# Technical references

相册兼容性改进参考了 [qinjintian/qq-zone](https://github.com/qinjintian/qq-zone) 在提交
[`a298dfd`](https://github.com/qinjintian/qq-zone/commit/a298dfd1754ac04e7b218131cc325d91fd99d6ca) 中公开的接口行为。

独立实现时采用的接口事实：

- 相册列表使用 `data.albumList`、`data.nextPageStart` 和 `data.albumsInUser` 分页。
- `hostUin` 是目标账号，`uin` 是当前登录账号。
- 照片接口可能通过 `Set-Cookie` 下发 `qq_photo_key`，后续相册请求及媒体下载需要续用。
- 原图字段优先级包含 `raw`、`origin_url` 和 `url`。
- 视频或实况图需要浮层接口解析真实视频地址。
- `rawshoottime`/`uploadtime` 可用于恢复本地文件时间线。

本项目未复制参考仓库的 Go 源码；Python API、数据模型、下载器、HTML 页面和测试均在本项目中独立实现。
