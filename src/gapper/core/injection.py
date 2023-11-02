import importlib.util
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Optional, Self, Sequence, Set

import typer


@dataclass
class InjectionHandler:
    content_to_be_injected: Set[Path] = field(default_factory=set)
    injection_module_name: str = field(default="injection")
    auto_injected_folder_name: str = field(default="gap_injection")
    injection_module_flag: str = field(default="__gap_injection_module__")

    def setup(
        self, auto_inject: bool | Path, inject_module_paths: Sequence[Path]
    ) -> Self:
        """Setup the injection handler.

        :param auto_inject: Whether to auto inject the injection folder.
        :param inject_module_paths: The paths to the modules to be injected.
        """
        if auto_inject:
            self.find_auto_injection(
                auto_inject if isinstance(auto_inject, Path) else None
            )
        if inject_module_paths:
            self.content_to_be_injected.update(inject_module_paths)

        return self

    @property
    def is_valid(self) -> bool:
        """Whether this config is valid.

        inject files must but files
        inject dirs must be directories
        """
        for content in self.content_to_be_injected:
            if not content.exists():
                return False

        return True

    def create_injection_module(self) -> ModuleType:
        """Create the injection module.

        :raises ValueError: If the module already exists.
        """
        import sys  # pylint: disable=import-outside-toplevel

        import gapper  # pylint: disable=import-outside-toplevel, cyclic-import

        module_full_name = f"gapper.{self.injection_module_name}"

        if (
            hasattr(gapper, self.injection_module_name)
            or module_full_name in sys.modules
        ):
            raise ValueError(f'Module "{module_full_name}" already exists.')

        new_module = ModuleType(module_full_name)
        setattr(new_module, self.injection_module_flag, True)
        setattr(gapper, self.injection_module_name, new_module)

        sys.modules[module_full_name] = new_module

        return new_module

    def inject(self, mod: Optional[ModuleType] = None) -> None:
        """Inject the specified files and those in dirs into the module.

        :param mod: The module to inject into. If not specified, a new module will be created.
        :raises ValueError: If no module to inject into.
        """
        module: ModuleType | None = mod or self.create_injection_module()

        if not module:
            raise ValueError("No module to inject into.")

        for file_path in self.content_to_be_injected:
            _inject_content(module, file_path)

    def find_auto_injection(self, path: Path | None = None) -> None:
        """Find the auto injection folder.

        :param path: The path to start searching from. If not specified, the current working directory will be used.
        """
        path = path or Path.cwd()

        self.content_to_be_injected.add(
            _find_injection_dir(self.auto_injected_folder_name, path)
        )


def _grab_user_defined_properties(module: ModuleType) -> Set[str]:
    """Grab all the properties defined in the module."""
    if hasattr(module, "__all__"):
        return set(module.__all__)
    else:
        return {name for name in dir(module) if not name.startswith("_")}


def _inject_content(module: Optional[ModuleType], content_path: Path) -> None:
    if content_path.is_dir():
        for sub_content in content_path.iterdir():
            _inject_content(module, sub_content)
    elif content_path.is_file():
        if content_path.suffix != ".py":
            typer.secho(
                f"Skipping {content_path} as it is not a python file", fg="yellow"
            )
            return

        spec = importlib.util.spec_from_file_location(content_path.name, content_path)
        if not spec:
            raise ValueError(f"Unable to load file {content_path} for injection")

        temp_module = importlib.util.module_from_spec(spec)

        if spec.loader is None:
            raise RuntimeError("Unable to load file for injection due to None loader")

        spec.loader.exec_module(temp_module)
        wanted_properties = _grab_user_defined_properties(temp_module)

        for wanted_property in wanted_properties:
            setattr(module, wanted_property, getattr(temp_module, wanted_property))


def _find_injection_dir(injection_dir: str, starting_dir: Optional[Path]) -> Path:
    """Find the injection directory."""
    target_folder = current_path = starting_dir

    # sort of wrong, but it's ok, who will make a folder in the root
    while current_path != current_path.parent:
        if (target_folder := current_path / injection_dir).exists():
            break

        current_path = current_path.parent

    if not target_folder.exists():
        raise ValueError(
            "No injection directory found. It's likely to be an config error. "
        )

    if not target_folder.is_dir():
        raise ValueError(f"Injection directory ({target_folder}) is not a directory")

    return target_folder
