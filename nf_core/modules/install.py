import os
import json
import questionary
import logging

import nf_core.utils

from .modules_command import ModulesCommand
from .module_utils import get_module_git_log, prompt_module_version_sha

log = logging.getLogger(__name__)


class ModulesInstall(ModulesCommand):
    def __init__(self, pipeline_dir, module=None, force=False, latest=False, sha=""):
        super().__init__(pipeline_dir)
        self.force = force
        self.latest = latest
        self.sha = sha
        self.module = module

    def install(self):

        # Check whether pipelines is valid
        self.has_valid_pipeline()

        # Get the available modules
        self.modules_repo.get_modules_file_tree()
        if self.latest and self.sha is not None:
            log.error("Cannot use '--sha' and '--latest' at the same time!")
            return False

        if self.module is None:
            self.module = questionary.autocomplete(
                "Tool name:",
                choices=self.modules_repo.modules_avail_module_names,
                style=nf_core.utils.nfcore_question_style,
            ).unsafe_ask()

        # Check that the supplied name is an available module
        if self.module not in self.modules_repo.modules_avail_module_names:
            log.error("Module '{}' not found in list of available modules.".format(self.module))
            log.info("Use the command 'nf-core modules list' to view available software")
            return False
        # Set the install folder based on the repository name
        install_folder = ["nf-core", "software"]
        if not self.modules_repo.name == "nf-core/modules":
            install_folder = ["external"]

        # Compute the module directory
        module_dir = os.path.join(self.pipeline_dir, "modules", *install_folder, self.module)

        # Load 'modules.json'
        modules_json_path = os.path.join(self.pipeline_dir, "modules.json")
        with open(modules_json_path, "r") as fh:
            modules_json = json.load(fh)

        current_entry = modules_json["modules"].get(self.module)

        if current_entry is not None and self.sha is None:
            # Fetch the latest commit for the module
            current_version = current_entry["git_sha"]
            git_log = get_module_git_log(self.module, per_page=1, page_nbr=1)
            if len(git_log) == 0:
                log.error(f"Was unable to fetch version of module '{self.module}'")
                return False
            latest_version = git_log[0]["git_sha"]
            if current_version == latest_version and not self.force:
                log.info("Already up to date")
                return True
            elif not self.force:
                log.error("Found newer version of module.")
                self.latest = self.force = questionary.confirm(
                    "Do you want install it? (--force --latest)", default=False
                ).unsafe_ask()
                if not self.latest:
                    return False
        else:
            latest_version = None

        # Check that we don't already have a folder for this module
        if not self.check_module_files_installed(self.module, module_dir):
            return False

        if self.sha:
            if not current_entry is None and not self.force:
                return False
            if self.download_module_file(self.module, self.sha, install_folder, module_dir):
                self.update_modules_json(modules_json, modules_json_path, self.module, self.sha)
                return True
            else:
                try:
                    version = prompt_module_version_sha(self.module, installed_sha=current_entry["git_sha"])
                except SystemError as e:
                    log.error(e)
                    return False
        else:
            if self.latest:
                # Fetch the latest commit for the module
                if latest_version is None:
                    git_log = get_module_git_log(self.module, per_page=1, page_nbr=1)
                    if len(git_log) == 0:
                        log.error(f"Was unable to fetch version of module '{self.module}'")
                        return False
                    latest_version = git_log[0]["git_sha"]
                version = latest_version
            else:
                try:
                    version = prompt_module_version_sha(
                        self.module, installed_sha=current_entry["git_sha"] if not current_entry is None else None
                    )
                except SystemError as e:
                    log.error(e)
                    return False

        log.info("Installing {}".format(self.module))
        log.debug(
            "Installing module '{}' at modules hash {}".format(self.module, self.modules_repo.modules_current_hash)
        )

        # Download module files
        if not self.download_module_file(self.module, version, install_folder, module_dir):
            return False

        # Update module.json with newly installed module
        self.update_modules_json(modules_json, modules_json_path, self.module, version)
        return True

    def check_module_files_installed(self, module_name, module_dir):
        """Checks if a module is already installed"""
        if os.path.exists(module_dir):
            if not self.force:
                log.error(f"Module directory '{module_dir}' already exists.")
                self.force = questionary.confirm(
                    "Do you want to overwrite local files? (--force)", default=False
                ).unsafe_ask()
            if self.force:
                log.info(f"Removing old version of module '{module_name}'")
                return self.clear_module_dir(module_name, module_dir)
            else:
                return False
        else:
            return True
