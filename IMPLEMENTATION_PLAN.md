# 实现计划

## 缺失的 Vendor 包
- [ ] vendor/group - 插件分组
- [ ] vendor/hmr - 热模块替换
- [ ] vendor/include - 插件包含机制
- [ ] vendor/loader - 插件加载器
- [ ] vendor/logger-console - 控制台日志
- [ ] vendor/timer - 定时器服务

## 缺失的 Core 包
- [ ] packages/core/agent-default-model - 默认模型配置
- [ ] packages/core/agent-tool-presentation - 工具展示层

## 需要完善的启动机制
- [ ] 实现 bundle 配置文件格式（YAML）
- [ ] 实现 plugin tree 的加载和启动流程
- [ ] 实现 profile 系统（对齐 dsh 的 profile-boot）

## 优先级
1. vendor/loader - 核心加载器
2. vendor/include - 插件包含
3. vendor/group - 插件分组
4. 缺失的 core packages
5. 完善启动机制
