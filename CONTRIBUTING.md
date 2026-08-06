# Contributing

感谢参与 Qzone Archive。

1. Fork 项目并从最新主分支创建功能分支。
2. 不要提交 `qzone_session.json`、Cookie、二维码、真实备份目录或包含个人信息的测试样本。
3. API 响应样本应匿名化，并优先转换为最小 fake API fixture。
4. 新增解析字段、分页逻辑或导出格式时，同时增加离线单元测试。
5. 提交前运行：

```bash
python3 -m unittest discover -s tests -v
python3 -m py_compile main.py qzone_scraper.py qzone_api/api/*.py
```

内部网页接口可能变化。提交兼容性修复时，请说明响应字段差异，并保持旧字段解析继续可用。
