# Jev 用于 Claude Code 上下文压缩的原理与基础逻辑

> 调研日期：2026-09-19
>
> 范围：公开可检索的 Claude Code + Jev 上下文/记忆压缩项目、文章、实践复盘、GitHub issue/PR 与社区讨论。
>
> 历史调研资料，不是当前 JEV 应用的运行依赖。当前应用没有 Claude、云端 Jev 或 API Key 调用链，见 [README](../../README.md)。

## 一、先给结论

目前真正的一手实现主要是 [tamaratran/fast-jev-compaction](https://github.com/tamaratran/fast-jev-compaction)。其余内容大多是对该项目的转载、安装验证、实验复盘或问题讨论。

它解决的不是模型权重意义上的“记忆”，也不建立跨会话长期记忆；它处理的是 Claude Code 当前会话里的 active context，也就是 `/compact` 或自动压缩时要继续发送给模型的历史记录。

它也不是传统意义上的摘要压缩。更准确的表述是：

> 让 Jev 判断每个历史工具调用是否还需要保留，然后以原文保留、只保留调用、截断结果或删除调用-结果对的方式减少上下文长度。

“保留部分不改写”可以称为 verbatim-preserving；整个过程仍然是有损的，因为被删除的工具结果可能无法恢复。

## 二、它试图替代什么

Claude Code 原生压缩通常会让模型把较长的历史整理成一份摘要。摘要更短，但可能丢掉：

- 精确的文件路径、命令参数和配置值；
- 完整的错误文本、编译输出和测试失败原因；
- 某次操作已经尝试过、因此不应再次尝试的事实；
- 某个历史结果对应的时间点、输入版本或外部数据状态。

fast-jev-compaction 的取舍是：不重写用户和助手文本，也不把保留的工具结果改写成摘要，而是把大量工具历史当作可选择的记录集合处理。

## 三、基础逻辑

### 1. 捕获一次 compaction 事件

插件挂在 Claude Code 的 `session.compact` function hook 上，覆盖手动 `/compact` 和自动 compaction。当前实现依赖 Claude Code 的 early-access function hooks，并要求启用相应环境变量和 TypeSafe/Jev API key。

### 2. 把历史拆成可管理的单位

每个 `tool_use` 和对应的 `tool_result` 通过 `tool_use_id` 配对。候选单位通常是一个完整的工具调用及其结果，而不是任意一段文本。

首条上下文和最近若干条消息会被固定保留；README 中的默认值包括保留最近 6 条消息。用户消息、助手消息本身不会在最终结果中被删改，主要候选是工具调用与工具结果。

### 3. 先制作给 Jev 判断的“决策状态”

为了让 Jev 能处理很长的历史，项目不会直接把全部工具结果原样送过去：

1. 工具输入先按多个阶段截短；
2. 长文本先保留头尾，再继续缩短；
3. 更老的非固定消息可折叠成省略标记；
4. 工具结果主体被替换为类似 `ok, 4213 chars (omitted)` 的短说明；
5. 必要时合并连续历史片段。

默认目标是让这份决策状态落在约 25K tokens 内，再为 Jev 的问题预留请求空间。

这一步很关键，也正是当前方案最大的争议来源：Jev 通常看得到工具名称、工具输入、消息顺序和结果长度，却看不到结果正文本身。

### 4. 对每个工具调用问两个问题

实现会对每个非固定工具调用发出两类 `noul` 问题：

1. `keepCall`：这个工具调用及其输入是否仍然对当前任务有用？
2. `keepResult`：这个工具结果的原文是否仍然必须保留，并且重新运行工具也不能可靠得到同样内容？

问题会分批发送；每批重复携带完整的决策状态，以避免单个请求超过 Jev 的请求上限。多个批次可以并发执行。

### 5. 把分数映射成三种动作

默认采用 `keepThreshold=0.5` 一类的阈值逻辑：

| 判断结果 | 对历史的处理 |
|---|---|
| `keepResult` 达到阈值 | 原样保留工具调用和完整结果 |
| 结果不保留，但 `keepCall` 达到阈值 | 保留工具调用，结果只留下头部和省略说明 |
| 两者都低于阈值 | 删除整个调用-结果对 |

随后按照原始顺序重建 transcript，移除空消息，并保证不会留下没有对应结果的孤立工具结果。

### 6. 失败时回退

如果 Jev 请求失败、答案格式错误、历史无法压到请求上限，或者压缩幅度不足，插件会回退到 Claude Code 原生 compaction。这个回退是当前实现能用于实际工作的必要条件，而不是可有可无的附加功能。

## 四、用一句伪代码概括

```text
on Claude Code compaction:
    transcript = capture_session()
    pairs = pair_tool_use_with_tool_result(transcript)
    pinned = pin_first_and_recent_messages(pairs)
    protected = apply_deterministic_safety_rules(pairs)

    decision_state = fit_old_history_for_jev(transcript)
    decisions = ask_jev_for_each_candidate(decision_state)

    for pair in candidates:
        if result_score(pair) >= result_threshold:
            keep_call_and_result_verbatim(pair)
        else if call_score(pair) >= call_threshold:
            keep_call_and_truncate_result(pair)
        else:
            drop_pair(pair)

    compacted = rebuild_in_original_order(transcript)
    if failed_or_not_enough_reduction(compacted):
        return native_claude_compaction()
    return compacted
```

## 五、它和“摘要压缩”的根本区别

| 维度 | 原生摘要式 compaction | Jev 方案 |
|---|---|---|
| 核心动作 | 让模型重写历史 | 让分类/判断模型选择历史记录 |
| 保留内容 | 摘要中的信息 | 被选中的工具调用和结果原文 |
| 丢失方式 | 摘要遗漏或误述 | 工具记录被截断或删除 |
| 主要优点 | 能把多种信息重新组织 | 不改写保留下来的原文，速度可能很快 |
| 主要风险 | 摘要失真 | 删除了后来仍需要的历史事实 |
| 对历史结果的理解 | 摘要模型能读取结果正文 | 当前实现通常只把结果正文省略给 Jev |

因此，Jev 的本质不是“把一段文本压缩成更短的同义文本”，而是“预测哪些历史条目可以不再发送”。

## 六、帖子和 issue 里反复出现的关键问题

### 1. Jev 看不到结果正文，判断信号可能退化

[Issue #26](https://github.com/tamaratran/fast-jev-compaction/issues/26) 的 16 个 session 复盘显示，真实 Jev 和一个总是返回低分的 fake asker，在压缩比例和后续使用命中数上非常接近：约 87.7% 对 88.5% 的字符缩减，后续使用命中都为 16 次。

原因很直接：决策状态把结果正文替换成了“成功、多少字符、正文省略”，而问题又把“结果是否必须原样保留”和“能否重新运行”放在一起问。Jev 没有足够信息判断具体错误、输出或历史快照是否重要。

[PrimeLine 的独立评估](https://primeline.cc/blog/typesafe-jev-pre-registered-test)也把这个问题归结为问题设计和状态设计，而不是简单归咎于 Jev 模型本身。

### 2. `keepCall` 和 `keepResult` 可能不是同一尺度

[Issue #56](https://github.com/tamaratran/fast-jev-compaction/issues/56) 报告：在实际样本里，`keepResult` 经常落在约 0.2 到 0.3 以下，而 `keepCall` 可以到 0.6 或 0.7。使用同一个 0.5 阈值时，结果保留几乎变得不可达，甚至会把本应保护的源码修改或失败结果截断/删除。

该 issue 还报告过一次真实 session 中 141 个非固定工具调用全部被删，只剩固定内容。因此更合理的后续设计可能是：两个问题使用独立阈值、按目标压缩率进行排序选择，或者在“全部低分”时触发保护性回退，而不是只用一个绝对阈值。

### 3. 大历史会让“被评分的记录”从决策状态中消失

[Issue #52](https://github.com/tamaratran/fast-jev-compaction/issues/52) 指出，历史太长时，前置的 fit 阶段会先把老消息折叠或省略；随后 Jev 仍可能收到这些调用的提问，但在状态里已经看不到对应内容。这样得到的是对缺失对象的低信息判断。

同一 issue 还指出，问题措辞更像是在问“原文是否不可替代”，而不是“当前任务是否依赖它”。Read、Bash 等工具通常可以重跑，于是它们容易被判为不重要，即便某次输出实际包含关键事实。

### 4. “可以重跑”不等于“能够复原同一个历史事实”

[Issue #25](https://github.com/tamaratran/fast-jev-compaction/issues/25) 给出了最重要的语义风险：某次计算、估值、API 查询或测试结果依赖当时的输入、代码版本、外部数据或时间点。未来重跑可能得到一个新结果，而不是被删除的旧结果。

因此“可重跑”只能说明工具调用能再次执行，不能证明历史结果可恢复。对时间敏感的外部数据、失败输出、版本迁移结果、数据库查询和生成式工具结果，最好默认保护，或至少把它们放进可检索的不可变归档。

### 5. 删除失败记录可能造成循环重试

Reddit 的 [LLMDevs 讨论](https://www.reddit.com/r/LLMDevs/comments/1wjjpk0/compaction_isnt_summarization_anymore_but/)反复提出同一个担忧：如果删除了“已经试过且失败”的调用，后续模型可能不知道这条路径已经失败，再次尝试同样的命令或方案。

这不是抽象担忧。失败记录的价值往往不是结果文本本身，而是它改变了未来决策空间：某个参数组合无效、某个文件不存在、某个修复会引入回归。当前实现把失败记录作为普通工具历史处理时，必须有额外的确定性保护规则。

### 6. 中间删除可能影响前缀缓存和真实成本

社区讨论还担心：即使最终 token 数变少，在历史中间删除片段可能破坏服务端对原始前缀的缓存命中，使重建后的请求重新计算更多前缀。Jev 请求本身还会重复携带决策状态到多个 batch，因此“最终上下文更短”不自动等于“总 token 成本更低”。

仓库 README 也明确承认这一点：每个 batch 都可能重复发送完整状态，接近请求上限时会产生更多请求；成本和收益必须按完整 compaction 周期测量，而不能只看最终字符数。

### 7. 隐私边界不是本地压缩

韩文实践复盘 [fast-jev-compaction Claude Code 적용기](https://blog.kwt.co.kr/fast-jev-compaction-claude-code-verbatim-compaction/)审查了插件的数据流：会话状态会发送到 `api.typesafe.ai`；虽然工具结果正文在决策状态中通常被省略，但用户输入、工具输入和会话结构仍可能离开本机。

所以这不是“本地把 Claude Code 历史清理一下”。涉及客户代码、内部路径、凭据、个人数据或受监管数据时，需要先确认 TypeSafe/Jev 的数据保留、训练使用、区域和企业协议，再决定是否启用。

### 8. 当前还是早期功能，兼容性和保护机制仍在补齐

韩文实测指出，插件依赖 Claude Code 2.1.274+ 的 early-access function hook；旧版本会因为 `session.compact` 事件不存在而失败。仓库当前 issue 还涉及显式 compact 指令未传给 Jev、未完成工具调用、重复 tool ID、请求超时、并发批次上限和自动 compaction 锁等问题：

- [Issue #39：compact 指令没有进入 Jev 成功路径](https://github.com/tamaratran/fast-jev-compaction/issues/39)
- [Issue #32：未完成工具调用没有正确进入判断状态](https://github.com/tamaratran/fast-jev-compaction/issues/32)
- [Issue #31：重复 ID 或错误配对可能破坏删除边界](https://github.com/tamaratran/fast-jev-compaction/issues/31)
- [Issue #34：请求缺少明确超时/取消机制](https://github.com/tamaratran/fast-jev-compaction/issues/34)

## 七、一个重要的混合方案：Jev 选择，摘要补事实

仓库的 [PR #15](https://github.com/tamaratran/fast-jev-compaction/pull/15) 尝试过折中方案：先让 Jev 选择要删的工具记录，再把被删部分交给一次普通摘要，最后把摘要附在保留的原文前面。

这个方案在一个 smoke test 中把召回从 11/12 提升到 12/12，但耗时从不到 1 秒级显著增加到十几秒甚至几十秒，因此 PR 被关闭。它揭示了一个清晰的设计取舍：

- 只用 Jev：快、原文保留，但删除造成的信息缺口由后续模型承担；
- Jev 加摘要：事实召回更好，但失去“快速且不重写”的核心优势；
- 更稳妥的工程方案：Jev 只负责候选选择，关键事实进入结构化外部记忆或不可变索引，而不是把所有风险交给一次概率判断。

## 八、目前最合理的安全基础逻辑

如果要把这类系统用于真实 Claude Code 工作流，建议把它分成两层。

### A. 确定性保护层

在调用 Jev 以前，以下内容默认不能删除或至少不能只留调用：

- 用户原始任务、当前 compact 指令和项目约束；
- 最近的若干轮消息；
- 最近一次相关文件读取后紧接着的编辑依据；
- 所有 Edit/Write/Patch 操作的输入和结果摘要；
- 失败命令、测试失败、编译错误、回滚和明确的阻断信息；
- 未完成或异常的工具调用；
- 时间敏感、外部状态敏感、不可重复的 API/数据库/计算结果；
- Agent/Task 等可能包含子任务结论的调用；
- 凭据和敏感内容的脱敏副本，而不是原文外发。

### B. Jev 选择层

Jev 只在剩余候选中做排序或分级选择。问题最好改成：

> 当前任务后续是否依赖这次调用或结果？

而不是只问：

> 是否必须原样保留，且重新运行也无法得到？

最终还应设置：最小保留量、最大删除比例、全低分保护、按时间窗口评分、结果头尾取样和失败回退。压缩后要做结构校验，确保 tool-use/tool-result 配对、顺序和 compact 指令仍然有效。

## 九、怎样判断宣传中的效果

公开帖子中常见“156K 变 62K”或“约 1M 变 86K”的演示/社交媒体说法，但前者来自项目演示，后者属于转述，不能当作经过独立控制实验验证的普遍收益。

真正应该测的是四个指标：

1. 最终发送 token 数；
2. Jev 判断本身消耗的输入 token、请求次数、延迟和费用；
3. 后续任务对历史事实的召回率，包括失败路径和时间点结果；
4. 删除后是否出现重复尝试、错误修复、上下文重建或前缀缓存损失。

只看“压缩率”会鼓励过度删除，不能证明 Claude Code 的长期任务成功率提高。

## 十、最终判断

Jev 用于 Claude Code compaction 的基础思想很有吸引力：把“让模型重新写一份历史摘要”改成“让模型判断哪些历史记录不必再发送”，从而保留选中内容的原文，并在工具密集型会话中获得很高的表面压缩率。

但当前公开实现更像一个有潜力的实验性语义剪枝器，而不是已经证明安全的记忆系统。最大风险不在 Jev 能不能给出分数，而在于：它经常看不到被判断结果的正文；“可重跑”被误当成“可复原”；单一阈值的分数校准存在问题；删除失败记录可能改变后续行为；而且整个决策状态需要外发到第三方服务。

一句话概括：

> Jev 的核心不是压缩信息，而是预测信息的缺席是否会影响下一步；这个预测只有在结果可见、保护规则充分、失败可回退并且隐私边界明确时，才适合进入生产工作流。
