from finlongrag.core.config import Settings


def test_settings_project_root_points_to_project_directory():
    settings = Settings.from_file()

    assert settings.project_root.name == "FinLongRAG"
    assert settings.config_path.name == "finlongrag.yaml"

