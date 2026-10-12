"""
`lectionary moravian` keeps working when moravian.org hasn't published
today's entry yet: it warns and runs on the newest entry (the CLI has no
button UI to ask, unlike the web /generate flow).
"""

from datetime import date
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from lectionary_engines.cli import main
from lectionary_engines.text_fetcher import StaleMoravianEntry


@patch("lectionary_engines.cli.save_study", return_value="out.md")
@patch("lectionary_engines.cli.display_study")
@patch("lectionary_engines.cli.ThresholdEngine")
@patch("lectionary_engines.cli.ClaudeClient")
@patch("lectionary_engines.cli.Config")
@patch("lectionary_engines.cli.TextFetcher")
def test_moravian_command_warns_and_uses_newest_entry_when_stale(
    mock_fetcher_cls, mock_config_cls, _claude, mock_engine_cls, _display, _save
):
    mock_config_cls.load.return_value = MagicMock(
        validate_api_key=MagicMock(return_value=True), output_directory="."
    )
    fetcher = mock_fetcher_cls.return_value
    fetcher.fetch_moravian.side_effect = [
        StaleMoravianEntry(date(2026, 10, 11), date(2026, 10, 12)),
        ("Psalm 23 | (Moravian text from Sunday, October 11, 2026)", "some text"),
    ]
    mock_engine_cls.return_value.generate.return_value = {"content": "study"}

    result = CliRunner().invoke(main, ["moravian", "threshold"])

    assert result.exit_code == 0, result.output
    assert "not published yet" in result.output
    assert "Sunday, October 11" in result.output
    assert fetcher.fetch_moravian.call_args_list[1].kwargs == {"allow_stale": True}
    mock_engine_cls.return_value.generate.assert_called_once()
