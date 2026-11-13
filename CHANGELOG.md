# Changelog

## Unreleased

A new skill `/lanekeeper:update` gets a new version and brings an existing hub folder up to the new templates, so you no longer compare files with `templates/hub/` by hand. The dashboard now shows which session started which, and the 3D office can be resized by dragging the line under it.

The skill itself comes with this version. The first time, run `claude plugin marketplace update lanekeeper` and `claude plugin update lanekeeper@lanekeeper`, type `/reload-plugins`, and then call `/lanekeeper:update` in the hub session ([Updating](https://github.com/holiday0726/lanekeeper/blob/main/README.md#updating), [한국어](https://github.com/holiday0726/lanekeeper/blob/main/README.ko.md#업데이트)).

### Added

- `skills/update` and `scripts/update_hub.py <hub folder>`. The skill updates the plugin, shows the old and new version with the CHANGELOG in between, and previews what would change in the hub folder. Nothing is written until you say yes; then `--apply` backs up to `<hub folder>/.lanekeeper/backup-<time>/` first.
- Rule documents (`CLAUDE.md`, `COORDINATION.md`) get a three way merge with `git merge-file`: your lines stay and only template changes go in. Settings JSON (`.claude/settings.json`, `supervisor.settings.json`) gets only top level keys that are new since the template copy, so a key you deleted is not added back. Without a template copy nothing is added. Where both sides changed the same place, or for nested settings such as new permission lines, the file is left alone and shown for you to merge by hand. `--accept <file>` marks it as reviewed.
- `STATUS.md`, `agents.json`, `decisions.json` and `dev-occupancy.json` are your data. They are created when missing and otherwise never changed. A data JSON file that lacks a top level key of the new template gets a note (for example `lanes` in `agents.json` from 0.6.0).
- User settings get the same "add missing keys only" merge as in `/lanekeeper:setup`.
- `--restore <backup folder>` puts the hub folder back as it was before `--apply`, including hand merges done after it, files it created and the template copies.

### Changed

- README "Manual install" and "Updating": a local marketplace also runs from a copy under `~/.claude/plugins/cache/`, so after `git pull` run the two update commands as well. Before, it said `git pull` and `/reload-plugins` were enough.
- Dashboard, Agents tab: a session started by another session with `claude --bg` sits under it in the flow chart, indented away from the hub and joined to it instead of to the hub, so the hub, a supervisor and the sessions the supervisor started show as three levels (and deeper). A branch goes to the busy side when anyone in it is busy. List cards say `상위 <name>` (parent), and a card whose starter has closed says `띄운 세션 <name> 닫힘` (started by, closed) when that starter was itself started with `claude --bg`, so a hub session that was opened again is not reported. The link comes from the starter's own transcript: a Bash call whose command runs `claude --bg` and the job id in that call's output (`backgrounded · <id>`, `claude attach <id>` or `started a copy as <id>`). Starters are matched by session id only, never by name, so nothing is guessed. Sessions without such a record stay right under the hub, as before. The first read of all transcripts runs in the background, so the hierarchy shows from the next refresh.
- Dashboard, 3D office: drag the line under the office (mouse or touch), or focus it and press the up and down arrows, to change the office height. Below 120px it folds away and stops drawing, and the line stays to pull it back. The height is kept in the browser and the room is framed again at each size. It grows up to 85% of the window or the height where the room fills the width, whichever is smaller.
- `/lanekeeper:setup` also keeps a copy of each file it copies in `<hub folder>/.lanekeeper/base/`. The update compares against these copies. A hub folder made with 0.6.0 or earlier has none, so its first update shows the full difference between your files and the new templates.

## 0.6.0

Lanes are now enforced, the writing skills moved out, tests run in CI, and the 3D office is optional.

If you used `humanizer`, `git-message` or the git message check, install [Addy-skills](https://github.com/holiday0726/Addy-skills) 1.1.0 or later and turn on `git_message_check` there again (`claude plugin configure addy-skills@addy-skills`). To enforce lanes in an existing hub folder, add `"lanes"` to its `agents.json` (see `templates/hub/agents.json`). Without it only the hub folder is protected, as before.

### Added

- Lane write guard `hooks/lane_guard.py`, replacing `hub_only_write.py`. The hub's `agents.json` gets `"lanes": {"<lane>": ["<path>", ...]}`. The hub folder always belongs to the hub. A session's lane comes from the folder it was opened in, and a worktree under `<repo>/.claude/worktrees/` counts as that repository. Edit, Write, MultiEdit and NotebookEdit outside the session's own lane are blocked with a message to ask the hub. The deepest path wins when lanes overlap, and a session in no lane may not write to any owned path.
- The same hook checks Bash on a best effort basis only: redirects (`>`, `>>`), `tee`, `sed -i`, `cp`, `mv`, `install` and a plain `cd`. Variables, scripts, `git` and PowerShell get through. It catches mistakes and is not a security boundary.
- Setting `lane_message_hub_only` (default off): workers may `SendMessage` only to the hub (a name whose `lane` is `HUB` in `agents.json`) and to `main`. Replies to a `uds:` address still go through.
- `scripts/lane_deny.py <hub folder>` prints `permissions.deny` lines (`Edit(//<path>/**)`) for the hub session from the lanes.
- Optional dashboard token: set `LANEKEEPER_TOKEN` and the server answers only a browser that opened `/?token=<value>` once (HttpOnly cookie). It keeps other accounts on the same PC out. The session start message shows that address.
- GitHub Actions runs the tests on Linux and Windows and `claude plugin validate --strict` on every push.

### Changed

- The 3D office is off by default. The Agents tab opens with the flow chart or card list, and the `3D 오피스` (3D office) button turns the office on and only then loads three.js and `js/office.js`. The choice is kept in the browser.
- `dashboard/index.html` is split into `app.css` and ten files under `dashboard/js/` by feature.
- All tests are pytest tests now (`python3 -m pytest -q`).
- `/api/transcript` answers 400 instead of 500 when `from` is not an integer.
- README: shorter "Moving from the old name" and "Manual install" sections, and "Addy-skills (optional)" and "Settings" as their own sections.
- The architecture diagram shows two hooks.

### Removed

- `skills/humanizer`, `skills/git-message`, the git message check hook and the setting `git_message_check`. They are in Addy-skills 1.1.0.

## 0.5.1

Updates to the hub rule templates and the humanizer skill. An update does not touch your hub folder, so copy the lines you want from `templates/hub/CLAUDE.md` and `templates/hub/COORDINATION.md` into it by hand.

### Changed

- `templates/hub/CLAUDE.md`: up to 8 task sessions may run at once (was 4). A new line says the user sets this cap and that changing it means changing the subsession sentence in `supervisor.settings.json` too. The example `examples/supervisor.settings.json` now says subsessions count toward the cap of 8.
- `skills/humanizer/SKILL.md`: a new rule at the top. Never use middle dots, dashes, arrows or a hyphen that joins two words. Keep a hyphen only where an ID, path, URL, command, code, branch name or date already has one. Two grep lines check the result. The rule comes before a writing sample and before the exceptions in §8 and §10.

### Added

- `templates/hub/CLAUDE.md`, optional merge delegation. When the user allows it, the hub has the lane session merge an MR that was verified in dev. Release and production still need the user's confirmation. A repository whose own rules say the user merges stays an exception, and the hub gives the user the MR link instead.
- `templates/hub/CLAUDE.md`: a restarted hub session gets a new address, so lane reports can fail to arrive. After a restart the hub sends each running lane session one message saying the hub is back and reports go to the same name.
- `templates/hub/COORDINATION.md`: when a worker's message to the hub fails, it saves the report to a file in its workspace and sends it again with the next hub message.
- README step 6 under [Set up the hub folder](https://github.com/holiday0726/lanekeeper/blob/main/README.md#set-up-the-hub-folder) ([한국어](https://github.com/holiday0726/lanekeeper/blob/main/README.ko.md#허브-폴더-만들기)): set the session cap and decide on merge delegation.

## 0.5.0

A new dashboard design. Nothing to change in your settings or your hub folder. After updating, stop the dashboard that is already running so the new one can start ([Updating](https://github.com/holiday0726/lanekeeper/blob/main/README.md#updating), [한국어](https://github.com/holiday0726/lanekeeper/blob/main/README.ko.md#업데이트)).

### Changed

- The Agents tab opens with an isometric 3D office. Each session has a desk and the hub has its own seat. A working session sits at a lit screen, a waiting one shows an orange `!`, and a resting one walks to the lounge. A new `[배정]` (assignment) from the hub flies a sheet to that desk and a `[보고]` (report) flies one back. Drag to turn the room, click a person to open the session. Without WebGL the office is hidden and the page starts at the flow chart.
- Below the office, a flow chart puts the hub in the middle and links each session to it, with message counts from the last 24 hours. The card list is still there as the second view.
- The Flow tab graph is tilted 3D by default, with arcs for the edges. Drag or use the arrow keys to turn it, or switch back to the flat view.
- At 1000px or wider the tabs move to a sidebar, and the usage meters become rings at its foot.
- New colours: near-black surfaces in steps with one orange accent (#E2560B). The state "입력 필요" (needs input) is now "대기 중" (waiting) and is orange in both themes. Card outlines are gone.
- `#/demo` adds buttons that change a session's scene in your browser only, to try the scenes. Nothing is sent to the sessions.
- Internal names are cleaned out of the examples and test data. The git message examples, the dashboard tests and the notes in `dashboard/README.md` now use neutral sample names and no readings from one machine.

### Added

- three.js r128 (`dashboard/vendor/three.min.js`, `OrbitControls.js`, MIT, `dashboard/vendor/three-LICENSE`), bundled so the page still needs no CDN.
- README section [Updating](https://github.com/holiday0726/lanekeeper/blob/main/README.md#updating) ([한국어](https://github.com/holiday0726/lanekeeper/blob/main/README.ko.md#업데이트)): the two update commands, turning on auto-update in the Marketplaces screen of `/plugin`, stopping the old dashboard, and what an update leaves alone (hub folder, settings, logs).
- The dashboard server sends its plugin version in an `X-Lanekeeper-Version` header. When a hub session opens and the running server is from another version, the session start message says to stop it and open the session again. It checks only the local server and never goes online.
- New screenshots and a short demo GIF in both READMEs, taken with sample data.

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
