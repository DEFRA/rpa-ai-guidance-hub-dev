import asyncio
import os
import pathlib


async def main():
    base_dir = pathlib.Path.cwd()

    if not (base_dir / "pyproject.toml").exists():
        print("Warning: pyproject.toml not found in cwd; run this from project root")

    git_base_url = "https://github.com/DEFRA"
    services_path = base_dir / "service-compose"
    repos_path = base_dir / "repos"

    repos_path.mkdir(parents=True, exist_ok=True)

    services = [f for f in os.listdir(services_path) if f.endswith((".yaml", ".yml"))]

    tasks = []

    for service in services:
        key = service.replace(".yaml", "").replace(".yml", "")

        clone_url = f"{git_base_url}/{key}.git"

        task = clone_repo(clone_url, repos_path, key)
        tasks.append(task)

    await asyncio.gather(*tasks)


async def clone_repo(clone_url: str, repos_path: pathlib.Path, repo_name: str):
    repo_dir = repos_path / repo_name

    if repo_dir.exists():
        print(f"Skipping clone: {repo_name} already exists at {repo_dir}")
        return

    process = await asyncio.create_subprocess_exec(
        "git",
        "clone",
        clone_url,
        cwd=repos_path,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    _, stderr = await process.communicate()

    if process.returncode == 0:
        print(f"Successfully cloned {clone_url}")
    else:
        print(f"Failed to clone {clone_url}: {stderr.decode()}")


if __name__ == "__main__":
    asyncio.run(main())
