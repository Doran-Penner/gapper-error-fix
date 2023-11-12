import asyncio
import logging
import traceback
from functools import wraps
from pathlib import Path
from time import time
from typing import Annotated, List, Optional

import typer

from gapper.cli.rich_test_check_output import rich_print_test_check
from gapper.cli.rich_test_result_output import rich_print_test_results
from gapper.connect.api.account import GSAccount
from gapper.connect.api.assignment import GSAssignmentEssential
from gapper.connect.gui.app_ui import GradescopeConnect
from gapper.connect.gui.upload_app_ui import AutograderUploadApp
from gapper.connect.gui.utils import DEFAULT_LOGIN_SAVE_PATH, add_debug_to_app
from gapper.core.file_handlers import AutograderZipper
from gapper.core.injection import InjectionHandler
from gapper.core.problem import Problem, build_connect_config
from gapper.core.result_synthesizer import ResultSynthesizer
from gapper.core.tester import Tester
from gapper.gradescope.datatypes.gradescope_meta import GradescopeSubmissionMetadata
from gapper.gradescope.main import run_autograder
from gapper.gradescope.vars import (
    AUTOGRADER_METADATA,
    AUTOGRADER_OUTPUT,
    AUTOGRADER_SUBMISSION,
    AUTOGRADER_TESTER_PICKLE,
)
from gapper.logger_utils import setup_root_logger

app = typer.Typer()

cli_logger = logging.getLogger("gapper.cli")

ProblemPathArg = Annotated[
    Path, typer.Argument(help="The path to the problem python file.")
]
SubmissionPathArg = Annotated[
    Path, typer.Argument(help="The path to the submission file.")
]
TesterConfigPathOpt = Annotated[
    Path,
    typer.Option(
        "--config",
        "-c",
        help="The path to the tester config file.",
        default_factory=lambda: Path.cwd() / "default.toml",
        dir_okay=False,
    ),
]
SavePathOpt = Annotated[
    Path,
    typer.Option(
        "--save-path",
        "-s",
        help="The directory to save the generated tester file.",
        default_factory=lambda: Path.cwd(),
    ),
]
VerboseOpt = Annotated[
    bool,
    typer.Option(
        "--verbose",
        "-v",
        help="Whether to run in verbose mode.",
    ),
]
UIDebugOpt = Annotated[
    bool,
    typer.Option(
        "--ui-debug",
        "-d",
        help="Whether to run in verbose mode.",
    ),
]
MetadataOpt = Annotated[
    Optional[Path],
    typer.Option(
        "--metadata",
        "-m",
        help="The path to the submission metadata file.",
        default_factory=lambda: None,
        dir_okay=False,
    ),
]
AutoInjectOpt = Annotated[
    bool,
    typer.Option(
        "--auto-inject",
        "-a",
        help="Whether to auto inject the tester file.",
        default_factory=lambda: False,
    ),
]
InjectOpt = Annotated[
    List[Path],
    typer.Option(
        "--inject",
        "-i",
        help="The path to the tester file to inject.",
        default_factory=list,
    ),
]
OverwriteConfirmOpt = Annotated[
    bool, typer.Option("--confirm-overwrite", "-y", is_flag=True)
]
UploadOpt = Annotated[
    bool,
    typer.Option(
        "--upload", "-u", is_flag=True, help="Whether to upload the autograder."
    ),
]
UseGUIOpt = Annotated[
    bool,
    typer.Option(
        "--gui",
        "-g",
        is_flag=True,
        help="Whether to use the GUI to upload.",
    ),
]
LoginSavePath = Annotated[
    Path,
    typer.Option(
        "--login-save-path",
        "-l",
        help="The path to save the login info.",
    ),
]


def _timed[T](fn: T) -> T:
    @wraps(fn)
    def wrapper(*args, **kwargs):
        start = time()
        result = fn(*args, **kwargs)
        end = time()
        cli_logger.debug(f"Time elapsed: {end - start}s")
        return result

    return wrapper


@app.command()
@_timed
def check(
    path: ProblemPathArg,
    auto_inject: AutoInjectOpt,
    inject: InjectOpt,
    verbose: VerboseOpt = False,
) -> None:
    """Check if the problem is defined correctly again the gap_check fields."""
    setup_root_logger(verbose)

    InjectionHandler().setup(auto_inject, inject).inject()
    cli_logger.debug("Injection setup")

    problem = Problem.from_path(path)
    cli_logger.debug("Problem loaded")

    cli_logger.debug("Start test checking")
    try:
        for test in problem.generate_tests():
            checked_result = test.check_test()
            rich_print_test_check(
                test.test_param.format(),
                checked_result,
                (
                    test.test_param.param_info.gap_expect,
                    test.test_param.param_info.gap_expect_stdout,
                ),
            )
    except Exception as e:
        typer.echo(f"Error: {e}")
        raise typer.Exit(code=1)


def _load_from_path(login_save_path: Path) -> GSAccount:
    try:
        account = GSAccount.from_yaml(login_save_path).spawn_session()
    except Exception as e:
        typer.secho(
            typer.style(
                f"Cannot load login info due to error {e}.\n"
                + "".join(traceback.format_tb(e.__traceback__)),
                fg=typer.colors.RED,
                bold=True,
            )
        )
        typer.echo("Please check your login save path.")
        typer.echo("If you haven't logged in, please use the login command.")
        raise typer.Exit(code=1)

    return account


def _check_login_valid(account: GSAccount) -> None:
    try:
        asyncio.run(account.login(remember_me=True))
    except Exception as e:
        typer.secho(
            typer.style(
                f"Cannot login due to error {e}.\n"
                + "".join(traceback.format_tb(e.__traceback__)),
                fg=typer.colors.RED,
                bold=True,
            )
        )
        typer.echo("Please check your login info.")
        raise typer.Exit(code=1)


def _upload_with_gui(login_save_path: Path, autograder_path: Path) -> None:
    gs_app = GradescopeConnect(
        login_save_path=login_save_path, autograder_path=autograder_path
    )
    gs_app.run()


def _upload_with_connect_details(
    cid: str, aid: str, login_save_path: Path, autograder_path: Path
) -> None:
    account = _load_from_path(login_save_path)
    _check_login_valid(account)

    gs_assignment = GSAssignmentEssential(cid, aid, session=account.session)
    gs_app = AutograderUploadApp(
        assignment=gs_assignment, autograder_path=autograder_path
    )
    gs_app.run()


@app.command()
@_timed
def upload(
    autograder_path: Annotated[
        Path,
        typer.Argument(
            exists=True,
            help="The path to the autograder zip file.",
        ),
    ],
    use_ui: UseGUIOpt = False,
    login_save_path: LoginSavePath = DEFAULT_LOGIN_SAVE_PATH,
    url: Annotated[
        Optional[str], typer.Option("--url", "-u", help="The url to the autograder.")
    ] = None,
    cid: Annotated[
        Optional[str], typer.Option("--cid", "-c", help="The course id.")
    ] = None,
    aid: Annotated[
        Optional[str], typer.Option("--aid", "-a", help="The assignment id.")
    ] = None,
    ui_debug: UIDebugOpt = False,
) -> None:
    """Upload an autograder to Gradescope."""
    add_debug_to_app(ui_debug)

    if use_ui:
        _upload_with_gui(login_save_path, autograder_path)
    else:
        if url:
            typer.echo("Using url to upload. Ignoring cid and aid.")
            connect_config = build_connect_config(url)
        else:
            typer.echo("Using cid and aid to upload.")
            connect_config = build_connect_config(cid, aid)

        _upload_with_connect_details(
            connect_config.cid, connect_config.aid, login_save_path, autograder_path
        )


@app.command()
@_timed
def login(
    confirm_store: Annotated[
        bool, typer.Option("--confirm-store", "-s", is_flag=True)
    ] = False,
    confirm_overwrite: OverwriteConfirmOpt = False,
    login_save_path: LoginSavePath = DEFAULT_LOGIN_SAVE_PATH,
    verbose: VerboseOpt = False,
) -> None:
    """Login to Gradescope."""
    setup_root_logger(verbose)

    email = typer.prompt("Enter your gradescope email")
    password = typer.prompt("Enter your gradescope password", hide_input=True)
    account = GSAccount(email, password).spawn_session()
    _check_login_valid(account)

    if confirm_store or typer.confirm(
        "Confirm you want to store your session?", default=True
    ):
        if (
            not login_save_path.exists()
            or confirm_overwrite
            or typer.confirm("File already exists. Overwrite?", default=False)
        ):
            account.to_yaml(login_save_path)
            typer.echo(f"Login info saved to {login_save_path.absolute()}")
            return

    typer.secho(typer.style("Aborted.", fg=typer.colors.RED, bold=True))


@app.command()
@_timed
def gen(
    path: ProblemPathArg,
    autograder_save_path: SavePathOpt,
    auto_inject: AutoInjectOpt,
    inject: InjectOpt,
    confirm_overwrite: OverwriteConfirmOpt = False,
    verbose: VerboseOpt = False,
    upload_flag: UploadOpt = False,
    use_ui: UseGUIOpt = False,
    login_save_path: LoginSavePath = DEFAULT_LOGIN_SAVE_PATH,
    ui_debug: UIDebugOpt = False,
) -> None:
    """Generate the autograder for a problem."""
    add_debug_to_app(ui_debug)
    setup_root_logger(verbose)

    InjectionHandler().setup(auto_inject, inject).inject()
    cli_logger.debug("Injection setup")

    problem = Problem.from_path(path)
    cli_logger.debug("Problem loaded")

    tester = Tester(problem)
    cli_logger.debug("Tester generated from problem")

    if autograder_save_path.is_dir():
        autograder_save_path = (
            autograder_save_path / f"{problem.expected_submission_name}.zip"
        )

    if confirm_overwrite or typer.confirm(
        f"File {autograder_save_path.absolute()} already exists. Overwrite?",
        default=True,
    ):
        typer.echo("Overwriting...")
        AutograderZipper(tester).generate_zip(autograder_save_path)
        typer.echo(
            f"Autograder zip generated successfully at {autograder_save_path.absolute()}"
        )
    else:
        typer.echo("Aborted.")
        return

    if upload_flag:
        if use_ui:
            _upload_with_gui(login_save_path, autograder_save_path)
        else:
            if problem.config.gs_connect is not None:
                _upload_with_connect_details(
                    problem.config.gs_connect.cid,
                    problem.config.gs_connect.aid,
                    login_save_path,
                    autograder_save_path,
                )
            else:
                typer.echo(
                    "No Gradescope connection info found in problem config. "
                    "Please use @gapper.connect() decorator, or use the --gui flag."
                )
                raise typer.Exit(code=1)


@app.command()
@_timed
def run(
    path: ProblemPathArg,
    submission: SubmissionPathArg,
    metadata_path: MetadataOpt,
    auto_inject: AutoInjectOpt,
    inject: InjectOpt,
    verbose: VerboseOpt = False,
    total_score: float = 20,
) -> None:
    """Run the autograder on an example submission."""
    setup_root_logger(verbose)

    cli_logger.debug(
        f"Try loading metadata from {metadata_path and metadata_path.absolute()}"
    )
    metadata = (
        None
        if metadata_path is None
        else GradescopeSubmissionMetadata.from_file(metadata_path)
    )
    cli_logger.debug(f"Metadata loaded: {metadata}")

    total_score = metadata.assignment.total_points if metadata else total_score
    cli_logger.debug(f"Total score is set to: {total_score}")

    InjectionHandler().setup(auto_inject, inject).inject()
    cli_logger.debug("Injection setup")

    problem = Problem.from_path(path)
    cli_logger.debug("Problem loaded")

    tester = Tester(problem)
    cli_logger.debug("Tester generated from problem")

    test_results = tester.load_submission_from_path(submission).run(metadata)
    cli_logger.debug("Test results generated from tester")

    score_obtained = ResultSynthesizer(
        results=test_results, total_score=total_score
    ).synthesize_score()
    cli_logger.debug(f"Score obtained from synthesizer {score_obtained}")

    rich_print_test_results(test_results, score_obtained, total_score)


@app.command()
@_timed
def run_in_prod(
    tester_path: Annotated[
        Path,
        typer.Argument(help="The path to the tester pickle file."),
    ] = AUTOGRADER_TESTER_PICKLE,
    submission_dir: Annotated[
        Path,
        typer.Argument(help="The path to the submission directory."),
    ] = AUTOGRADER_SUBMISSION,
    metadata_file: Annotated[
        Path,
        typer.Argument(
            help="The path to the submission metadata file.",
        ),
    ] = AUTOGRADER_METADATA,
    output_file: Annotated[
        Path,
        typer.Argument(help="The path to the output file."),
    ] = AUTOGRADER_OUTPUT,
    verbose: VerboseOpt = True,
) -> None:
    """Run the autograder in production mode."""
    setup_root_logger(verbose)

    cli_logger.debug("Autograder run in production mode")
    run_autograder(tester_path, submission_dir, metadata_file, output_file)
    cli_logger.debug("Autograder run finished")


__all__ = ["app"]
