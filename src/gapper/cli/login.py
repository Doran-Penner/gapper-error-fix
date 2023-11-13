from typing import Annotated

import typer

from gapper.cli.cli_options import LoginSavePath, OverwriteConfirmOpt, VerboseOpt, timed
from gapper.cli.utils import check_login_valid
from gapper.connect.api.account import GSAccount
from gapper.connect.gui.utils import DEFAULT_LOGIN_SAVE_PATH
from gapper.logger_utils import setup_root_logger


@timed
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
    check_login_valid(account)

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
