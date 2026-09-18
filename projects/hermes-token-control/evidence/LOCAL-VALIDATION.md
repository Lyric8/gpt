# 本次本地验证记录

状态：LOCAL_TESTS_PASS / PRODUCTION_NOT_INTEGRATED / GITHUB_NOT_PUSHED_AT_PACKAGE_CREATION。

环境：Linux，Python 3.13.5，Git 2.47.3。执行 `python -m unittest discover -s tests -v`：**67 tests, 12.554s, OK**。原始控制台输出见 `tests.txt`。`python -m compileall -q hermes_token_control bin tests` 通过。

67 项包括核心故障条件、显式审批扩容而不清零、真实本地临时 Git 仓库多文件发布、读回、并发拒绝以及 278 字符历史文件名。未连接真实模型、微信、浏览器、用户 state.db 或生产 systemd；GitHub 写入未完成。

`provider.py` 的测试使用 fake client 和明确标为 test-fixture 的计数器，不是线上 tokenizer 精度或真实 token 性能证明。`git_observer.py` 与发布 helper 的 Git 测试使用本地 bare 仓库，不证明 GitHub 账号实际写权限。

`projection.json` 是显式假设计算，保守 18.86%、目标 10.48%、压力 28.09% 均不是实测优化结果。只有完成 INTEGRATION.md 的真实接入、同工作量对照与可靠性门禁后才能宣布达标。
