# AD · Egern 广告净化模块

目前收录：**腾讯视频净化（Egern 适配版）**。

## 安装

在 **Egern → 模块 → 右上角 `+` → 从 URL 添加**，粘贴：

```text
https://raw.githubusercontent.com/m20104600/AD/main/modules/txvideo-ad.egern.yaml
```

模块依赖的脚本地址（模块会自动引用，不用单独安装）：

```text
https://raw.githubusercontent.com/m20104600/AD/main/scripts/txvideo-ad.egern.js
```

1. 启用模块与 Egern 的 HTTPS 解密/MITM。
2. 安装 Egern CA 证书，并在 iOS **设置 → 通用 → 关于本机 → 证书信任设置**中信任它。
3. 关闭与本模块重复的腾讯视频重写规则，重新打开腾讯视频测试。
4. 更新模块后刷新模块配置；如果仍使用旧配置，删除模块后用上面的 URL 重新添加，再断开重连 Egern。

本模块需要支持 `export default async function(ctx)`、请求/响应 `arrayBuffer()` 及二进制脚本的 Egern 版本；不适用于 Quantumult X 的经典脚本执行环境。若 HTTPS 解密影响播放，可先停用本模块排查，不要为了本模块关闭系统证书验证。

## 来源与致谢

**原作者：TG@ZenMoFiShi；原项目：[ZenmoFeiShi/Qx](https://github.com/ZenmoFeiShi/Qx)。**

用户指定的原配置：

```text
https://raw.githubusercontent.com/ZenmoFeiShi/Qx/refs/heads/main/TxvideoAD.snippet
```

该配置引用的原脚本：

```text
https://raw.githubusercontent.com/ZenmoFeiShi/Qx/refs/heads/main/Txvideoad.js
```

本次适配基于上游提交 **`5921d619f843cd203aaf976631d71cada634ef3a`**。`upstream/` 保存对应源文件快照，`upstream/SOURCE.json` 记录原地址、固定提交和 SHA-256，便于核对来源。模块不是原作者发布的 Egern 官方版本，也不代表腾讯官方产品。

**本仓库由 m20104600 进行 Egern 格式与运行时适配，不把原脚本宣称为原创。** 抓取时上游 GitHub 未声明仓库许可证；此处不擅自给原作加 MIT 等新许可证，也不额外授予原作的再分发许可。原作权利归原作者，使用及后续分发需尊重原作者要求；如权利人提出异议，将及时处理。

## 适配内容

上游描述的目标包括开屏、播放前广告、部分底部标签及个人页面推广。这里保留原有处理逻辑，**不承诺所有腾讯视频版本和所有广告场景都有效**，不解锁会员权益或付费内容。

- 将 QX 的两条域名 `reject` 规则转换为 Egern 精确域名 `REJECT`。
- 原样保留四个 MITM 域名和五条请求/响应 URL 匹配，不扩大到整个腾讯域名。
- 请求阶段读取 `ctx.request.arrayBuffer()`，响应阶段读取 `ctx.response.arrayBuffer()`；SDK 配置使用 `ctx.response.text()`。
- 原脚本主体以本地词法适配层嵌入 Egern ES Module；没有 `eval`、没有远程运行时加载，TRPC / Protobuf / JCE / gzip 算法保持不变。
- 返回 Egern 支持的 `Uint8Array` 或字符串；修改内容后去掉旧 `Content-Length`，避免二进制被 UTF-8 字符串转换破坏。
- 二进制规则显式配置 `body_required: true`、`binary_body: true`；单次正文上限 4 MiB，脚本超时 15 秒、脚本刷新周期 1 小时。
- 不识别、读取失败或没有命中的报文不修改；不添加账号凭据、统计上报或额外网络请求。

## 验证范围

仓库包含离线回归测试：模块 YAML 结构、匹配正则与上游一一对应、二进制处理、gzip、原脚本输出对拍和异常透传。

**离线通过不等于 iOS App 实测通过。** 本仓库不伪造腾讯视频真实业务响应；测试中的报文是明确标记的人工协议夹具。最终去广告效果、客户端版本兼容性和播放稳定性仍需在 Egern 与腾讯视频 App 内实测。

## 开发与复现

需要 Node.js 22+、Python 3.11+ 和 PyYAML（仅校验 YAML 使用；手机端无依赖）：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
python3 tools/build.py
node --check scripts/txvideo-ad.egern.js
node --test tests/*.test.mjs
.venv/bin/python tests/validate_module.py
```

`tools/build.py` 会先检查上游快照哈希，再从 `tools/egern-wrapper.js.txt` 生成成品。更新上游时请重新审核代码、固定提交和哈希并重跑测试，不要只修改来源记录。

## 目录

- `modules/txvideo-ad.egern.yaml`：Egern 模块入口。
- `scripts/txvideo-ad.egern.js`：可直接加载的 Egern 脚本。
- `upstream/`：原始配置、原始 JS 与来源记录。
- `tools/`：适配模板和可复现构建脚本。
- `tests/`：离线验证，不使用真实账号或 Token。
