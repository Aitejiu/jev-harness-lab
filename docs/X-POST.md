# X 发布文案（轻量版：测了 Jev 能做什么 + 做了小工具 + 双链接）

> 发布前把 `juejin.cn/post/XXXXXX` 换成实际文章链接；已按 X 规则核过字数（CJK×2、链接×23，≤280）。

## 版本 A（中文，267/280，推荐）

```
把 TypeSafe 的 Jev 测了一遍：看它在 Agent Harness 里能干点什么。

有些活意外地不错（注入检测、重排、skill 路由），有些完全不行。

顺手做了两个小工具：MCP server 和 jev_route_skill（帮主模型选 skill）。

详细测试和代码：
juejin.cn/post/XXXXXX
github.com/Aitejiu/jev-harness-lab
```

## 版本 B（英文，267/280）

```
Tested TypeSafe's Jev to see what a "decision model" can do in an agent harness — and built two small tools with it.

Some things worked well (injection, reranking, skill routing), others not at all.

Full tests & code:
juejin.cn/post/XXXXXX
github.com/Aitejiu/jev-harness-lab
```

## 版本 C（长文首帖，需 X Premium；同样的轻量口吻）

```
把 TypeSafe 的 Jev 测了一遍：一个不生成文本、只输出"带概率的结构化判断"的决策模型，
在 Agent Harness 里到底能干点什么。

结论：
· 有些活意外地不错：注入检测、检索重排、skill 路由、命令风险门控
· 有些活完全不行：预测"该不该上强模型"、长轨迹失败归因、非英语
· 顺手做了两个小工具：MCP server（注入扫描/命令风险/重排）+ jev_route_skill（帮主模型选 skill）

详细测试、数据和小工具都在这里：
掘金：juejin.cn/post/XXXXXX
代码：github.com/Aitejiu/jev-harness-lab
```

## 发布建议

- 免费账号直接发 **A**；英文受众发 **B**
- 链接降权顾虑：把掘金链接放第一条回复，正文只留 GitHub
- 话题标签：`#AI #Agents #LLM`、`#TypeSafe`
