# 墙缝夜行 · Mouse After Dark

第一人称 3D 老鼠潜行小游戏。躲开猫，穿过熄灯后的厨房和储藏室。主菜单和联机大厅可切换中文或 English。

A first-person 3D mouse stealth game. Sneak past the cat and explore a dark kitchen and pantry. Each player can switch between Chinese and English.

## 试玩 · Play

在 GitHub 上点 **Code → Download ZIP**，解压后用浏览器打开 `index.html`。

On GitHub, choose **Code → Download ZIP**, unzip it, and open `index.html` in a browser.

- **单人 / Single player** — 找齐三个数字，尝试不同排列来打开墙洞。 Collect three digits and try different orders to open the wall lock.
- **双人 / Co-op** — 笼外玩家找奶酪并传递举爪和吱声暗号，笼内玩家踩亮踏板、拨灯并扳动扣件。 One mouse finds cheese and signals with paws and squeaks. The other powers the cage lock and sets its switch and latches.

### 同 Wi‑Fi 联机 · Same-Wi-Fi co-op

两台设备连同一个 Wi‑Fi。开房电脑需要 Python 3.10 或更新版本。在 Mac 上可双击 `Start-LAN.command` 或 `Start-LAN-English.command`，也可以在项目目录运行以下命令。

Connect both devices to the same Wi-Fi. The host computer needs Python 3.10 or later. On macOS, open either launcher or run this command from the project folder.

```sh
python3 Start-LAN.py
# English startup
python3 Start-LAN.py --lang en
```

在打开的页面选 **联机双人 → 创建房间**，复制邀请链接给队友。队友打开链接并点 **加入房间**。联机期间保持启动窗口打开。

In the browser, choose **Two-Player Co-op → Host Room** and share the invite link. Your partner opens it and selects **Join Room**. Keep the launcher running during play.

## 更新 · Updates

`index.html` 是游戏的源文件，浏览器和 Wi‑Fi 启动器都使用它。改动在这个仓库里提交，旧版本可以在 **Commits** 中找到。已下载的本地文件需要重新下载才能获得更新。

`index.html` is the game source for both the browser and the Wi-Fi launcher. Changes are committed in this repository, and older versions are available in **Commits**. Download a fresh copy to update local files.

部署到 GitHub Pages 时可使用 `main` 分支的根目录。Pages 提供静态游戏页面。同 Wi‑Fi 模式由开房电脑运行 Python 启动器。

For GitHub Pages, the root of `main` contains the static game entry point. The Python launcher runs on the host computer for same-Wi-Fi play.
