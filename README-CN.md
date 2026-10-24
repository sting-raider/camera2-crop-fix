# OnePlus 15T Camera2 Crop Fix

[English](README.md)

> **上游问题跟踪：** [LineageOS/issues#853](https://github.com/LineageOS/issues/issues/853)
>
> 调查与修复进展请查看该报告。

可开关、可撤销的 Magisk / APatch 模块，用于修正 **OnePlus 15T（PLZ110）特定 LineageOS 构建**上的裁切元数据重复缩放。适用于独立打开物理后摄的相机路径，修正预览与静态照片倍率不一致，以及 10× 裁切尺寸过小造成的拍照失败。

**当前为预发布版，仅适配一组已验证的设备与系统文件。** 其他版本会被拒绝，即使版本名称相近。

## 使用条件

| 项目 | 支持范围 |
| --- | --- |
| 设备 | OnePlus 15T / PLZ110 |
| LineageOS | `24.0-20261011-NIGHTLY-fairlady` |
| Build ID | `CP2A.260605.016` |
| 相机路径 | 物理后摄 ID `2`、`3` |
| Root 管理器 | 已测试 Magisk 30.7；更高版本仍须通过相同检查。APatch 11039 或更新版本（需 Action 功能），尚未实机测试 |

安装和运行时还会核对相机服务及相关库的完整哈希，具体见 [profile.json](profile.json)。当前安装包不支持 KernelSU。

## 安装与开关

1. 从 [Releases](https://github.com/hackroid/camera2-crop-fix/releases) 下载模块 ZIP，勿使用 GitHub 自动生成的源码 ZIP。
2. 打开 **Magisk → 模块 → 从本地安装** 或 **APatch → 系统模块 → 安装**，选择 ZIP，安装后重启。使用 APatch 时，安装、更新或卸载任何模块后请完整重启，不要用 **软重启**；应用了模块变更的软重启会使修正以故障状态关闭。
3. 关闭相机应用，在 Magisk 或 APatch 中找到本模块，点 **操作**（APatch 中为 **执行**）启用。
4. 再点一次同一按钮暂停；请求的开关状态会在重启后保留。

`flag=1` 表示开启，`flag=0` 表示暂停。`verified=0` 表示当前相机服务进程尚未处理匹配的相机结果。首次启用可能重启相机服务；同一已核对进程内的暂停、恢复无需重启服务。

首次安装默认暂停，更新保留原有开启请求。测试版手动下载安装，正式版再接入 Magisk 自动更新。

### 卸载与恢复

在 Magisk 或 APatch 中卸载后重启（APatch 需完整重启），即可恢复原版系统程序。模块只使用临时文件挂载，不写入系统分区。

如需立即完整回退，请先关闭相机应用，再运行：

```sh
su -mm -c 'sh /data/adb/modules/camera2_native_zoom_fix/control.sh restore'
```

检测到故障后，模块会关闭修正并阻止自动重试。系统或库文件更新后，需要重新验证适配。清除故障状态前，请先阅读[原理与恢复说明](doc/architecture.md)。

## 修正边界

- 修正独立打开物理后摄 `2`、`3` 时的裁切元数据。
- 覆盖 10× 取整边界和受支持的拍照／预览请求类型。
- 保留原始 mapper 的调用与返回值。
- 使用文件承载的原生代码，无需新增 SELinux 规则、Frida、Zygisk 或 Vector。

逻辑相机 `0` 的自动选镜、应用自身选镜和应用后处理不在本模块范围内。该模块不是通用相机修复或画质配置。

## 构建与贡献

开发流程见 [CONTRIBUTING.md](.github/CONTRIBUTING.md)，构建方法见 [building.md](doc/building.md)，GitHub 发布设置见 [releasing.md](doc/releasing.md)。发布 ZIP 只携带小型原生补丁，安装时从设备上已核对的原版程序生成修正后的相机服务。仓库和发布包不分发完整系统／厂商二进制、照片或诊断日志。

欢迎 fork 后提交 PR。

使用 [Apache-2.0](LICENSE) 许可证。
