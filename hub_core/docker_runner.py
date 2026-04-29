import os
import shutil
import subprocess

DEFAULT_DOCKER_IMAGE = "graph-making-hub:latest"


def rerun_in_docker(hub_path, root_dir, argv, *, image=DEFAULT_DOCKER_IMAGE, build=False):
    docker_bin = shutil.which("docker")
    if not docker_bin:
        raise RuntimeError("Docker is not installed or not available on PATH.")

    hub_path = os.path.abspath(hub_path)
    root_dir = os.path.abspath(root_dir)

    if build:
        _build_docker_image(docker_bin, hub_path, image)

    filtered_args = [arg for arg in argv if arg not in {"--docker", "--docker-build"}]

    command = [
        docker_bin,
        "run",
        "--rm",
        "-e",
        "RESEARCH_HUB_IN_DOCKER=1",
        "-e",
        "PYTHONUNBUFFERED=1",
        "-v",
        f"{root_dir}:{root_dir}",
        "-w",
        hub_path,
        image,
        "python",
        "orchestrator.py",
        *filtered_args,
    ]

    print("\n🐳 [Docker Mode]")
    print(f"   - image: {image}")
    print(f"   - root_mount: {root_dir}")

    try:
        proc = subprocess.run(command, check=False, timeout=3600)
    except subprocess.TimeoutExpired:
        print("   ❌ Docker run timed out (3600s limit)")
        return 1
    return proc.returncode


def _build_docker_image(docker_bin, hub_path, image):
    print("\n🐳 [Docker Build]")
    print(f"   - image: {image}")
    build_cmd = [
        docker_bin,
        "build",
        "-t",
        image,
        hub_path,
    ]
    try:
        proc = subprocess.run(build_cmd, check=False, timeout=600)
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"Docker build timed out (600s) for image: {image}")
    if proc.returncode != 0:
        raise RuntimeError(f"Docker build failed for image: {image}")
