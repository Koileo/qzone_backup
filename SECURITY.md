# Security Policy

## Sensitive files

`qzone_session.json`、`QR.png` 和 `backups/` 可能含账号凭据或个人内容。它们默认被 Git 忽略；发布代码前仍应检查 `git status` 与提交内容。

## Reporting

发现凭据泄露、路径穿越、HTML 注入或依赖风险时，请通过仓库维护者提供的私密安全联系方式报告，并在修复发布前避免公开真实凭据或可识别的备份数据。

## Supported versions

安全修复目前只应用到主分支最新版本。
