# Changelog

## 0.4.1

### Changed

- The session start message no longer assumes SSH. When opening the Orca tab fails, it no longer points to Orca's SSH settings and instead says to allow the orca CLI in Orca or turn off the `orca` setting. Without the `orca` command there is still no Orca text at all.
- The session start message now always ends with a pointer to the README section "다른 PC 에서 보기" (Viewing from another PC). It does not guess whether the session is remote.

### Added

- README section [Viewing from another PC](https://github.com/holiday0726/lanekeeper/blob/main/README.md#viewing-from-another-pc) ([한국어](https://github.com/holiday0726/lanekeeper/blob/main/README.ko.md#다른-pc-에서-보기)): same PC, clients that forward ports (VS Code/Cursor Remote, Orca), and clients without port forwarding such as Paseo (`ssh -N -L <port>:127.0.0.1:<port> <user>@<host>`). The dashboard still listens only on `127.0.0.1`.
- `/lanekeeper:setup` gives the same guidance at the end instead of assuming an SSH client.

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

Settings do not carry over, because they are stored per plugin name and removed together with the old plugin. Write them down, uninstall `agent-hub@agent-hub`, remove the `agent-hub` marketplace, install `lanekeeper`, and enter the settings again. If you used the git message check, set `git_message_check` to `true`. Step by step: [Moving from the old name](https://github.com/holiday0726/lanekeeper/blob/main/README.md#moving-from-the-old-name) ([한국어](https://github.com/holiday0726/lanekeeper/blob/main/README.ko.md#옛-이름에서-옮기기)).
