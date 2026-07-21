from pathlib import Path
import unittest


class ContainerPackagingTests(unittest.TestCase):
    def test_dockerfile_rebuilds_mock_data_before_serving_demo(self) -> None:
        dockerfile = Path("Dockerfile").read_text(encoding="utf-8")

        self.assertIn("python -m autoops ingest mock_data --db data/autoops.db --rebuild", dockerfile)
        self.assertIn("python -m autoops serve --host 0.0.0.0 --port 8000", dockerfile)
        self.assertIn("EXPOSE 8000", dockerfile)

    def test_requirements_include_api_dependencies(self) -> None:
        requirements = Path("requirements.txt").read_text(encoding="utf-8").splitlines()

        self.assertIn("fastapi", requirements)
        self.assertIn("uvicorn", requirements)
        self.assertIn("pydantic", requirements)

    def test_dockerignore_excludes_local_environment(self) -> None:
        dockerignore = Path(".dockerignore").read_text(encoding="utf-8")

        self.assertIn(".venv", dockerignore)
        self.assertIn("__pycache__", dockerignore)


if __name__ == "__main__":
    unittest.main()
