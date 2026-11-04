# Changelog

## 0.4.0

This release renames the plugin. Existing users need to reinstall.

### Changed

- Renamed the plugin and the marketplace from `agent-hub` to `lanekeeper`, and the repository from `claude-hub-plugin` to `lanekeeper`. Commands are now `/lanekeeper:setup`, `/lanekeeper:humanizer`, `/lanekeeper:git-message` and `claude plugin install lanekeeper@lanekeeper`.
- The git message check hook (`git-message-style.py`) is now off by default. Turn it on with the new setting `git_message_check=true`.
- Installing the Addy-skills plugin is now optional. `/lanekeeper:setup` asks first and does not install it by default, and the hub template uses those skills only when the plugin is installed.

### Added

- English `README.md`. The Korean text moved to `README.ko.md`. The hub rule templates and the skill documents stay in Korean.
- Setting `git_message_check` (boolean, default `false`).
- Dashboard demo GIF at the top of both READMEs.

### Moving from agent-hub

Settings do not carry over, because they are stored per plugin name and removed together with the old plugin. Write them down, uninstall `agent-hub@agent-hub`, remove the `agent-hub` marketplace, install `lanekeeper`, and enter the settings again. If you used the git message check, set `git_message_check` to `true`. Step by step: [Moving from the old name](README.md#moving-from-the-old-name) ([한국어](README.ko.md#옛-이름에서-옮기기)).
