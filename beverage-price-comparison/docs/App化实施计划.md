# 安卓 APK 化实施计划

- **文档版本**：v0.1
- **目标**：把现有「Web 前端 + FastAPI 后端」比价系统发布成**安卓 APK**。
- **关联**：[真实上线需求文档.md](真实上线需求文档.md) · [部署流水线.md](部署流水线.md) · [设计文档.md](设计文档.md) · 决策 [决策记录.md](决策记录.md) ADR-014

> ⚠️ 本文档是实施蓝图。**沙盒环境无 Android SDK/Gradle，无法在此实际构建 APK**；本文给出可复制的命令与配置，真实构建需在装有 Android Studio 的机器上执行。

---

## 0. 头号架构认知（先想清这个）⭐

**APK 里装的是「客户端」，不是「整套系统」。** 后端是 Python/FastAPI，**不能打进 APK**——它必须**部署在服务器上**（复用现有 [部署流水线.md](部署流水线.md) 的阿里云/火山云），APK 通过 HTTPS 调它的 API。

```
┌─────────── 安卓 APK（WebView 客户端）───────────┐        ┌──── 云端（已有部署流水线）────┐
│  现有 web/ 页面（app/discover/团购）             │  HTTPS │  FastAPI 后端                 │
│  + 原生定位插件（解决 iframe 定位限制）          │ ─────▶ │  /search /compare /api/tuangou│
│  + 指向云端 API 的 BASE_URL                      │        │  真实适配器 + 账户 + DB        │
└──────────────────────────────────────────────────┘        └──────────────────────────────┘
```

**现有代码的直接影响**：前端全部用**相对路径**（`fetch('/search')`），靠 FastAPI 同源伺服。APK 里 WebView 加载的是**本地打包文件**，相对路径会失效——必须改为**可配置的绝对 API 地址**（见 §2）。这是转 APK 最核心的一处改造。

---

## 1. 技术选型：Capacitor（WebView 壳）

| 方案 | 出 APK | 复用现有 web/ | 结论 |
| --- | --- | --- | --- |
| **Capacitor** ⭐ | Gradle 构建 | ✅ 几乎全复用 | **选它**：现有三入口页面直接装壳，原生插件补定位，最快出 APK |
| uni-app | ✅ | 逻辑复用、UI 重写 | 想同时出小程序再考虑 |
| React Native / Flutter | ✅ | ❌ UI 全重写 | 要独立原生体验时才值得 |
| TWA（PWA 壳）| ✅ | ✅ | 依赖已上线 HTTPS 站点 + 需 Play 校验，国内分发不便 |

选 **Capacitor**：最大化复用已建好的 `web/app.html`、`discover.html`、团购页面，用官方 Gradle 链路产出 APK，原生 Geolocation 插件顺带解决「iframe 内定位不弹窗」的历史遗留。

---

## 2. 前端改造（转 APK 的关键改动）

### 2.1 API 地址可配置（相对 → 绝对）
现状：`fetch('/search')`、`fetch('/compare?...')`、`fetch('/export')`、`fetch('/grids')`、`fetch('/grid/resolve')`、`/api/tuangou/*` 全是相对路径。

改造：引入统一 `API_BASE`，所有请求走 `API_BASE + path`：
```js
// web/config.js（新增）——APK 内指向云端后端；本地开发留空即同源
window.API_BASE = window.API_BASE || "https://api.你的域名.com";
```
把各页面 `fetch('/xxx')` 改为 `fetch(API_BASE + '/xxx')`（集中封装一个 `api(path, opts)` 更稳）。

### 2.2 原生定位替代浏览器定位
现有 `navigator.geolocation` 在 WebView 里权限体验差 → 换 `@capacitor/geolocation`，拿到经纬度再调 `/grid/resolve`。**这一步顺带解决历史遗留「定位真实弹窗需独立 HTTPS 页面」**——原生插件是系统级权限弹窗。

### 2.3 deeplink 跳转下单
团购 CPS deeplink（`/api/tuangou/compare` 返回的 `deeplink`）用 `@capacitor/browser` 或系统 Intent 打开外部 App（美团/抖音），承接转化闭环（PRD P2-1）。

### 2.4 后端 CORS
后端 `CORS_ORIGINS` 需允许 APK 的来源（Capacitor 为 `https://localhost` / `capacitor://localhost`）。配置已是环境变量驱动（`app/config.py`），加白名单即可。

---

## 3. 构建步骤（可复制命令）

```bash
# ① 初始化前端工程（把 web/ 作为静态资源目录）
npm init -y
npm install @capacitor/core @capacitor/cli @capacitor/android \
            @capacitor/geolocation @capacitor/browser @capacitor/app
npx cap init "饮品团购比价" "com.bpc.compare" --web-dir=web

# ② 加安卓平台（生成 android/ Gradle 工程）
npx cap add android

# ③ 每次改完 web/ 同步进原生工程
npx cap copy android
npx cap sync android

# ④ 构建 APK（二选一）
#   A. 命令行：
cd android && ./gradlew assembleDebug        # 产出 debug APK（免签名，自测用）
#   → android/app/build/outputs/apk/debug/app-debug.apk
#   B. 图形界面：npx cap open android → Android Studio 里 Build > Build APK(s)
```

### capacitor.config.json（关键配置）
```json
{
  "appId": "com.bpc.compare",
  "appName": "饮品团购比价",
  "webDir": "web",
  "server": { "androidScheme": "https" },
  "plugins": {
    "Geolocation": { "permissions": ["location"] }
  }
}
```

### AndroidManifest 权限（android/app/src/main/AndroidManifest.xml）
```xml
<uses-permission android:name="android.permission.INTERNET"/>
<uses-permission android:name="android.permission.ACCESS_FINE_LOCATION"/>
<uses-permission android:name="android.permission.ACCESS_COARSE_LOCATION"/>
```

---

## 4. 签名与发布 APK

```bash
# ① 生成签名密钥（keystore 必须妥善保管，丢失无法更新同一应用）
keytool -genkey -v -keystore bpc-release.keystore \
        -alias bpc -keyalg RSA -keysize 2048 -validity 10000

# ② 构建 release APK 并签名（在 android/app/build.gradle 配置 signingConfigs 后）
cd android && ./gradlew assembleRelease
#   → android/app/build/outputs/apk/release/app-release.apk
```
- **直接分发**：把 `app-release.apk` 放官网/二维码下载；用户需允许「未知来源安装」。
- **应用商店**：国内华为/小米/OPPO/vivo/应用宝等，**需软件著作权 + 主体资质 + ICP**；Google Play 用 AAB 而非 APK（国内一般不走）。

---

## 5. 分阶段落地（与真实上线对齐）

| 阶段 | 内容 | 依赖 |
| --- | --- | --- |
| **M1 可跑 APK（Mock）** | 前端 API_BASE 改造 + Capacitor 装壳 + 原生定位 → 出 debug APK 连**已部署的 Mock 后端**。**最小验证见 [安卓平板测试版方案.md](安卓平板测试版方案.md)**（Tier 0 零改动浏览器直连 / Tier 1 薄壳 APK 侧载）| 后端先按部署流水线上云 |
| **M2 真实数据** | Mock 适配器换真实（CPS/联盟授权）+ 账户体系（P2-7）+ HTTPS 域名 + ICP 备案 | 平台授权、备案 |
| **M3 发布** | release 签名 APK + 埋点漏斗（P2-4）接 `/metrics` + 商店资质上架 | 软著/资质 |

## 6. 复用 vs 新建边界

| 能力 | 处理 |
| --- | --- |
| 后端 API（`/search /compare /api/discover /api/tuangou/*`）、部署流水线、限流/可观测 | ✅ **复用**（后端零重写，仅加 CORS 白名单） |
| 三入口页面 HTML/JS 逻辑 | ✅ **复用**（改 API_BASE + 原生定位插件调用） |
| Capacitor 工程、原生权限、签名、商店上架 | 🆕 **新建** |
| 真实数据适配器、账户、DB、ICP | 🆕 真实上线前置（与 Web 版共用，非 APK 特有） |

## 7. 硬前置与风险（绕不开）

1. **后端必须先上云**：APK 只是客户端，没有部署的后端 APK 就是空壳（M1 即依赖部署流水线）。
2. **真实价格依赖平台授权**：不接 CPS/联盟真实数据，APK 里仍是 Mock（界面「非真实价格」标注不得移除）。
3. **签名 keystore 唯一且不可丢**：丢失无法再更新同一应用。
4. **国内上架要资质**：软著 + 主体 + ICP；直接分发 APK 可绕商店但用户体验与信任成本高。
5. **诚实提醒**：本沙盒无 Android 构建环境，本文档为可执行蓝图，真实 APK 需在 Android Studio 机器上产出。
