import traceback
from pathlib import Path
from threading import Timer
from typing import cast

from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.containers import Container, ScrollableContainer
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Label, Select

from gapper.connect.api.assignment import DockerStatusJson, GSAssignment
from gapper.connect.api.utils import OSChoices


class Repeat(Timer):
    def run(self):
        while not self.finished.wait(self.interval):
            self.function(*self.args, **self.kwargs)


class AutograderUpload(Screen):
    BINDINGS = [("ctrl+b", "go_back", "Go Back")]

    CSS_PATH = "autograder_upload_ui.tcss"

    def __init__(
        self, *args, assignment: GSAssignment, autograder_path: Path, **kwargs
    ) -> None:
        super().__init__(*args, **kwargs)
        self.assignment = assignment
        self.autograder_path = autograder_path
        self.upload_info_timer: Timer | None = None

    def compose(self) -> ComposeResult:
        """Compose the autograder upload screen."""
        yield Header()
        yield Container(
            Label("Uploading Autograder For"),
            Label(f"Assignment: {self.assignment and self.assignment.name}"),
            Label(
                f"Autograder Path: {self.autograder_path and self.autograder_path.absolute()}"
            ),
        )
        yield Container(
            Label("Autograder OS:"),
            Select(
                ((case.name, case) for case in OSChoices),
                value=OSChoices.UbuntuV2204,
                id="os_select",
            ),
        )
        yield Button("Upload", id="upload_btn")
        yield Container(Label("Info"), ScrollableContainer(Label(id="info_label")))
        yield Container(Label("Error"), ScrollableContainer(Label(id="error_label")))

        yield Footer()

    @on(Button.Pressed, "#upload_btn")
    async def uploads(self) -> None:
        """Upload the autograder to the assignment with selected OS."""
        select: Select[OSChoices] = cast(
            Select[OSChoices], self.get_widget_by_id("os_select")
        )

        info_label = cast(Label, self.get_widget_by_id("info_label"))
        error_label = cast(Label, self.get_widget_by_id("error_label"))

        if select is None:
            error_label.update("The autograder OS is unset.")
            return

        try:
            await self.assignment.upload_autograder(self.autograder_path, select.value)
            info_label.update("Uploaded autograder successfully.")
        except Exception as e:
            error_label.update(
                "Cannot upload autograder due to Error.\n"
                f"{e}\n"
                f"{traceback.format_tb(e.__traceback__)}"
            )
        else:
            self.upload_info_timer = Repeat(
                1, lambda: self.run_worker(self.refresh_upload_info())
            )
            self.upload_info_timer.start()

    async def action_go_back(self) -> None:
        """Go back to the previous screen."""
        if self.upload_info_timer:
            self.upload_info_timer.cancel()

        await self.app.action_pop_screen()

    async def refresh_upload_info(self) -> None:
        self.log.debug("Refreshing upload info")
        error_label = cast(Label, self.get_widget_by_id("error_label"))
        info_label = cast(Label, self.get_widget_by_id("info_label"))
        docker_status: DockerStatusJson = self.assignment.get_docker_build_status()
        self.log.debug(f"Got docker status: {docker_status}")

        if docker_status["status"] == "built":
            self.log.debug("Docker image built successfully")
            self.upload_info_timer.cancel()
            info_header = "Docker image built"
        else:
            info_header = "Docker image building"

        info_label.update(Text(f'{info_header}\n{docker_status["stdout"]}'))
        error_label.update(Text(docker_status["stderr"] or "No Error"))

        self.log.debug("Refreshed upload info")
