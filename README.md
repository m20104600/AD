# 腾讯视频净化 · Egern

## 使用方法

1. 在 **Egern → 模块 → `+` → 从 URL 添加**，粘贴下面的模块链接：

```
https://raw.githubusercontent.com/m20104600/AD/main/modules/txvideo-ad.egern.yaml
```

2. 启用模块和 **HTTPS 解密（MITM）**，安装并信任 Egern CA 证书。
3. 关闭重复的腾讯视频重写规则，断开重连 Egern，再重新打开腾讯视频。

模块会自动加载脚本，无需单独安装 JS。更新时刷新模块；未生效可删除后用原 URL 重新添加。

[![复制模块链接](https://img.shields.io/badge/点击复制-模块链接-238636?style=for-the-badge)](https://m20104600.github.io/AD/)

点击上面的按钮进入复制页，再点「复制模块链接」。

## 来源

- 原作者：**TG@ZenMoFiShi**
- 原项目：[ZenmoFeiShi/Qx](https://github.com/ZenmoFeiShi/Qx)
- 原配置：[TxvideoAD.snippet](https://github.com/ZenmoFeiShi/Qx/blob/main/TxvideoAD.snippet)
- 原脚本：[Txvideoad.js](https://github.com/ZenmoFeiShi/Qx/blob/main/Txvideoad.js)

本仓库仅做 Egern 适配，原作权利归原作者。
