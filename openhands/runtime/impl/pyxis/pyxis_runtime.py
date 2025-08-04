"""SLURM/Pyxis runtime implementation for OpenHands."""

import atexit
import os
import subprocess
import time
from collections import namedtuple
from pathlib import Path
from typing import Callable, Optional

from openhands.core.config import OpenHandsConfig
from openhands.core.logger import openhands_logger as logger
from openhands.events import EventStream
from openhands.integrations.provider import PROVIDER_TOKEN_TYPE
from openhands.runtime.impl.action_execution.action_execution_client import (
    ActionExecutionClient,
)
from openhands.runtime.plugins import PluginRequirement
from openhands.runtime.utils.command import get_action_execution_server_startup_command

PyxisConfig = namedtuple(
    "PyxisConfig",
    ["sandbox_workspace_dir"],
)


class PyxisRuntime(ActionExecutionClient):
    """SLURM/Pyxis-based runtime implementation.

    This runtime uses SLURM with the Pyxis plugin to run containers.
    It uses pre-built Docker images and doesn't require a builder.
    """

    container_port: int = 30001
    action_execution_server_host: str = "http://localhost"

    def __init__(
        self,
        config: OpenHandsConfig,
        event_stream: EventStream,
        sid: str,
        container_image: str,
        plugins: Optional[list[PluginRequirement]] = None,
        env_vars: Optional[dict[str, str]] = None,
        status_callback: Optional[Callable] = None,
        attach_to_existing: bool = False,
        headless_mode: bool = True,
        user_id: Optional[str] = None,
        git_provider_tokens: Optional[PROVIDER_TOKEN_TYPE] = None,
    ):
        super().__init__(
            config,
            event_stream,
            sid,
            plugins,
            env_vars,
            status_callback,
            attach_to_existing,
            headless_mode,
            user_id,
            git_provider_tokens,
        )
        logger.debug(f"PyxisRuntime: {sid=}")

        self.config = config
        self._container_image = container_image
        self.container_name = f"openhands-runtime-{sid}"
        self.container_is_running = False
        self.slurm_job_id: Optional[str] = None
        self._plugins = plugins or []
        self._env_vars = env_vars or {}

        # Workspace configuration
        self.pyxis_config = self._init_pyxis_config()
        self.container_workspace_dir = "/workspace"

        # SLURM configuration from environment variables
        self.slurm_partition = os.environ.get("SLURM_PARTITION", "priority")
        self.slurm_account = os.environ.get("SLURM_ACCOUNT", "")
        self.slurm_time_limit = os.environ.get("SLURM_TIME_LIMIT", "4:00:00")
        self.slurm_cpus = os.environ.get("SLURM_CPUS", "4")
        self.slurm_memory = os.environ.get("SLURM_MEMORY", "16G")

        # Set up cleanup
        atexit.register(self.cleanup)

    def _init_pyxis_config(self) -> PyxisConfig:
        """Initialize Pyxis-specific configuration."""
        sandbox_workspace_dir = self.config.workspace_mount_path_in_sandbox
        if sandbox_workspace_dir is None:
            sandbox_workspace_dir = self.config.workspace_mount_path
        logger.debug(f"PyxisRuntime: {sandbox_workspace_dir=}")

        return PyxisConfig(
            sandbox_workspace_dir=sandbox_workspace_dir,
        )

    def _get_pyxis_env_vars(self) -> dict[str, str]:
        """Get environment variables to pass to Pyxis container."""
        env_vars = {}

        # Add OpenHands-specific environment variables
        env_vars["PYTHONPATH"] = "/openhands"
        env_vars["POETRY_VIRTUALENVS_PATH"] = "/opt/poetry"
        env_vars["POETRY_VIRTUALENVS_IN_PROJECT"] = "true"

        # Add user-provided environment variables
        if self._env_vars:
            env_vars.update(self._env_vars)

        # Add plugin environment variables from plugins
        for plugin in self._plugins:
            if hasattr(plugin, "env_vars") and plugin.env_vars:
                env_vars.update(plugin.env_vars)

        return env_vars

    def _get_pyxis_mounts(self) -> list[str]:
        """Get volume mounts for Pyxis container."""
        mounts = []

        # Mount workspace
        workspace_mount = self.config.workspace_mount_path
        if workspace_mount:
            mounts.append(f"{workspace_mount}:{self.container_workspace_dir}")

        # Mount cache directory
        cache_dir = self.config.cache_dir
        if cache_dir:
            mounts.append(f"{cache_dir}:/home/openhands/.cache")

        # Mount OpenHands source (for development)
        if hasattr(self.config, "mount_workspace") and self.config.mount_workspace:
            openhands_src = Path(__file__).parent.parent.parent.parent.parent
            mounts.append(f"{openhands_src}:/openhands:ro")

        return mounts

    def _check_slurm_available(self) -> bool:
        """Check if SLURM is available on the system."""
        try:
            result = subprocess.run(
                ["sinfo", "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return result.returncode == 0
        except (subprocess.SubprocessError, FileNotFoundError):
            return False

    def _build_srun_command(self, command: Optional[str] = None) -> list[str]:
        """Build the srun command with Pyxis options."""
        cmd = ["srun"]

        # SLURM options
        cmd.extend(["--job-name", self.container_name])
        cmd.extend(["--partition", self.slurm_partition])
        if self.slurm_account:
            cmd.extend(["--account", self.slurm_account])
        cmd.extend(["--time", self.slurm_time_limit])
        cmd.extend(["--ntasks", "1"])
        cmd.extend(["--cpus-per-task", self.slurm_cpus])
        cmd.extend(["--mem", self.slurm_memory])

        # Pyxis options
        cmd.extend(["--container-image", self._container_image])
        cmd.extend(["--container-name", self.container_name])
        cmd.extend(["--container-workdir", self.container_workspace_dir])

        # Add mounts
        mounts = self._get_pyxis_mounts()
        if mounts:
            mounts_str = ",".join(mounts)
            cmd.extend(["--container-mounts", mounts_str])

        # Add environment variables
        for key, value in self._get_pyxis_env_vars().items():
            cmd.extend(["--container-env", f"{key}={value}"])

        # Make container writable and map root user
        cmd.extend(["--container-remap-root"])

        # Add the command to execute if provided
        if command:
            cmd.extend(["bash", "-c", command])

        return cmd

    def _start_container(self) -> None:
        """Start the Pyxis container with action execution server."""
        logger.info(f"Starting Pyxis container {self.container_name}...")

        # Get the proper action execution server startup command
        startup_cmd = get_action_execution_server_startup_command(
            self.container_port,
            self._plugins,
            self.config,
        )

        # Convert command list to shell command string
        server_cmd = " ".join(startup_cmd)

        # Build srun command
        cmd = self._build_srun_command(server_cmd)

        logger.debug(f"Running command: {' '.join(cmd)}")

        # Start container in background
        self.container_process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        # Get the SLURM job ID
        self._get_slurm_job_id()

        # Wait for server to be ready
        self._wait_for_server()

        self.container_is_running = True
        logger.info(
            f"Container {self.container_name} started successfully with job ID {self.slurm_job_id}"
        )

    def _get_slurm_job_id(self) -> None:
        """Get the SLURM job ID for the running container."""
        # Wait a bit for job to be registered
        time.sleep(3)

        for _ in range(10):
            cmd = [
                "squeue",
                "--name",
                self.container_name,
                "--format",
                "%i",
                "--noheader",
            ]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode == 0 and result.stdout.strip():
                job_lines = result.stdout.strip().split("\n")
                if job_lines and job_lines[0].strip():
                    self.slurm_job_id = job_lines[0].strip()
                    logger.info(f"SLURM job ID: {self.slurm_job_id}")
                    return

            time.sleep(2)

        logger.warning("Could not determine SLURM job ID")

    def _wait_for_server(self, timeout: int = 300) -> None:
        """Wait for the action execution server to be ready."""
        logger.info("Waiting for action execution server to start...")

        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                response = self.session.get(
                    f"{self.action_execution_server_url}/alive",
                    timeout=5,
                )
                if response and response.status_code == 200:
                    logger.info("Action execution server is ready")
                    return
            except Exception as e:
                logger.debug(f"Server not ready yet: {e}")

            # Check if job is still running
            if self.slurm_job_id and not self._is_job_running():
                # Get job info for debugging
                self._get_job_info()
                raise RuntimeError("SLURM job terminated unexpectedly")

            time.sleep(5)

        raise RuntimeError(
            f"Action execution server failed to start within {timeout} seconds"
        )

    def _is_job_running(self) -> bool:
        """Check if the SLURM job is still running."""
        if not self.slurm_job_id:
            return False

        cmd = ["squeue", "--job", self.slurm_job_id, "--format", "%t", "--noheader"]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode == 0 and result.stdout.strip():
            state = result.stdout.strip()
            return state in ["R", "PD"]  # Running or Pending
        return False

    def _get_job_info(self) -> None:
        """Get detailed job information for debugging."""
        if not self.slurm_job_id:
            return

        cmd = ["scontrol", "show", "job", self.slurm_job_id]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode == 0:
            logger.info(f"Job info for {self.slurm_job_id}:\n{result.stdout}")
        else:
            logger.warning(f"Could not get job info: {result.stderr}")

    def _stop_container(self) -> None:
        """Stop the Pyxis container."""
        if self.slurm_job_id:
            logger.info(f"Cancelling SLURM job {self.slurm_job_id}...")

            cmd = ["scancel", self.slurm_job_id]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode != 0:
                logger.warning(f"Failed to cancel job: {result.stderr}")
            else:
                logger.info(f"SLURM job {self.slurm_job_id} cancelled")

        if hasattr(self, "container_process") and self.container_process:
            self.container_process.terminate()
            try:
                self.container_process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.container_process.kill()
                self.container_process.wait()

        self.container_is_running = False

    def _container_exists(self) -> bool:
        """Check if a container with this name exists in SLURM."""
        cmd = ["squeue", "--name", self.container_name, "--format", "%i", "--noheader"]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10,
        )

        return result.returncode == 0 and bool(result.stdout.strip())

    def _attach_to_container(self) -> None:
        """Attach to an existing Pyxis container.

        Note: This is complex with SLURM/Pyxis as we can't easily attach
        to a running job. For now, we'll raise an error.
        """
        raise NotImplementedError(
            "Attaching to existing Pyxis containers is not yet implemented. "
            "Please start a new container instead."
        )

    def _init_container(self) -> None:
        """Initialize a new Pyxis container."""
        if not self._check_slurm_available():
            raise RuntimeError("SLURM is not available on this system")

        # Check if container already exists
        if self._container_exists():
            logger.warning(f"Container {self.container_name} already exists in SLURM")
            self._stop_container()

        # Start the container
        self._start_container()

    async def connect(self) -> None:
        """Connect to the runtime."""
        if self.attach_to_existing:
            self._attach_to_container()
        else:
            self._init_container()

        # Runtime is now connected and ready

    def close(self) -> None:
        """Close the runtime and clean up resources."""
        if self.container_is_running:
            self._stop_container()

        super().close()

    def cleanup(self) -> None:
        """Cleanup method to be called on exit."""
        try:
            self.close()
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")

    def copy_to(
        self, host_src: str, sandbox_dest: str, recursive: bool = False
    ) -> None:
        """Copy files from host to container using volume mounts."""
        # Since we mount the workspace, files should already be accessible
        # This is mainly for files outside the mounted directories
        logger.warning(
            "copy_to may not work as expected with Pyxis - files should be accessible via mounts"
        )
        # Suppress unused parameter warnings
        _ = host_src, sandbox_dest, recursive

    def copy_from(self, path: str) -> Path:
        """Copy files from container to host using volume mounts."""
        # Since we mount the workspace, files should already be accessible
        # For Pyxis, we assume the path is already accessible via mounts
        return Path(path)

    def run_command(self, command: str) -> tuple[str, int]:
        """Run a command directly in the container (for testing/debugging)."""
        if not self.container_is_running:
            raise RuntimeError("Container is not running")

        # For debugging, we can submit a new job with the same container
        cmd = self._build_srun_command(command)

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
        )

        return result.stdout, result.returncode

    def get_working_directory(self) -> str:
        """Get the current working directory in the container."""
        return self.container_workspace_dir

    @property
    def action_execution_server_url(self) -> str:
        """Get the action execution server URL."""
        return f"{self.action_execution_server_host}:{self.container_port}"
