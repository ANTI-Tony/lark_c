# CUA-Lark · 飞书 AI 校园挑战赛 复赛作品

> 赛道:质量工程与智能测试方向
> 作品:**CUA-Lark** — 视觉驱动的飞书桌面端 Computer-Use Agent
> 仓库:https://github.com/ANTI-Tony/lark_c

---

## 一、个人信息

| 字段 | 内容 |
|---|---|
| **姓名** | 文敬博 |
| **参赛形式** | 个人独立完成 |
| **学校 · 专业** | 悉尼大学 软件工程荣誉学士 |
| **毕业时间** | 2026 年 11 月 |
| **后续计划** | 计划升读研究型硕士 1 年 |
| **学术成果** | 年底将有 2A + 1B 论文在投 / 接收(含 EMNLP) |

### 投递飞书 ByteIntern 实习岗位

| 字段 | 内容 |
|---|---|
| **意向地点** | 上海 / 北京 |
| **最快到岗时间** | 2026 年 12 月 1 日 |
| **期望方向** | 后训练(post-training)/ 基础设施(infra) |
| **可实习时长** | 6 个月以上长期 |

### 项目中负责的工作简述

独立完成全部架构设计、模型选型、代码实现、测试用例、文档与报告系统:从 5 层架构图到 1500+ 行 Python 实现,从 Sonnet 4.6 Computer Use 主循环到 Electron CDP 双通道断言,从 DSL 到 HTML 报告生成器,均独立产出。

---

## 二、项目结果展示

### 1. Demo 展示

**仓库地址**:https://github.com/ANTI-Tony/lark_c

**最快试用(macOS 三步):**

```bash
git clone https://github.com/ANTI-Tony/lark_c.git
cd lark_c
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env       # 填写 ANTHROPIC_API_KEY

# 启动飞书并暴露 Electron 调试端口(开启结构化断言通道)
open -a "Feishu" --args --remote-debugging-port=9222

# 跑预置的 IM 测试套件
python -m cua_lark.cli test tests/feishu/im/

# 一键生成可视化 HTML 报告
python -m cua_lark.cli report runs/
```

**CLI 入口**:

| 命令 | 用途 |
|---|---|
| `cua-lark run "<自然语言指令>"` | 单条指令驱动 — M1 演示场景 |
| `cua-lark test <用例目录> [--tag im] [--no-cdp]` | 批量跑测试用例 — M2 主入口 |
| `cua-lark report <runs目录>` | 自动生成自包含 HTML 报告 — M4 主入口 |

**Demo 视频脚本(3-5 分钟,3 段)**:

1. **30 秒 · 痛点开场**:展示传统 selector-based 测试(如 Playwright)在 UI 改版后批量失效的截图;用一句话点明 CUA 的价值。
2. **2.5 分钟 · 核心闭环**:屏幕分屏 — 左侧是 `cua-lark test tests/feishu/im/` 的实时输出,右侧是飞书桌面端,Agent 真实操作飞书 IM(打开聊天、输入消息、搜索、唤起 emoji 面板)。同步展示模型主动调用 `zoom` 自愈的关键帧(Sonnet 4.6 独占能力)。
3. **1 分钟 · 报告与价值**:`cua-lark report runs/` 一键生成 HTML 报告;打开浏览器展示截图轨迹 + 双通道断言结果 + 失败定位。

### 2. 核心代码展示

#### 2.1 五层架构

```
┌──────────────────────────────────────────────────────────────┐
│                        CUA-Lark Agent                        │
│                                                              │
│  Perception   →   Planner   →   Executor   →   Verifier      │
│   (screen,         (Claude        (PyAutoGUI     (VLM + CDP  │
│    CDP a11y)        CoT)           hotkeys)       asserts)   │
│                         │                                    │
│                         ▼                                    │
│                    Trajectory  →  HTML Report                │
└──────────────────────────────────────────────────────────────┘
```

每层职责见 `docs/DESIGN.md`:Perception 截图、Planner 规划、Executor 模拟操作、Verifier 双通道断言、Trajectory & Report 落地与可视化。

#### 2.2 Computer Use 主循环 — `cua_lark/agent.py`

```python
DEFAULT_MODEL = "claude-sonnet-4-6"
BETA_HEADER  = "computer-use-2025-11-24"   # 最新协议
TOOL_TYPE    = "computer_20251124"

tools = [{
    "type": TOOL_TYPE,
    "name": "computer",
    "display_width_px":  self.claude_dims[0],
    "display_height_px": self.claude_dims[1],
    "display_number": 1,
    "enable_zoom": True,                    # ← Self-Heal 开关
}]

for step in range(1, self.max_steps + 1):
    resp = self.client.beta.messages.create(
        model=self.model, system=SYSTEM_PROMPT,
        tools=tools, messages=messages, betas=[BETA_HEADER],
        max_tokens=4096,
    )
    if resp.stop_reason == "end_turn":
        break
    for tu in [b for b in resp.content if b.type == "tool_use"]:
        result, return_b64 = self._handle_action(dict(tu.input))
        # 把执行结果(截图 / zoom 裁剪图)封装为 tool_result 回传
        messages.append({"role": "user", "content": [...]})
```

设计要点:**完整保留消息历史**(包含 tool_use / tool_result),让模型在多步上下文中自主决策何时停步。

#### 2.3 Self-Heal · zoom 自愈 — `cua_lark/agent.py::_handle_zoom`

Sonnet 4.6 新增的 `zoom` 动作:模型对小元素坐标不确定时,主动指定一个矩形区域要求"放大看",我们裁剪截图后回传。**这是 4.6 独占的原语,我们直接将其用作 Self-Heal 的核心。**

```python
def _handle_zoom(self, tool_input):
    region = tool_input.get("region")     # [x1, y1, x2, y2] in Claude-space
    full_b64, (claude_w, claude_h) = capture_b64()
    x1, y1, x2, y2 = (clip(int(v)) for v in region)
    img = Image.open(io.BytesIO(base64.b64decode(full_b64)))
    cropped = img.crop((x1, y1, x2, y2))
    return ActionResult("zoom", ok=True), encode_b64(cropped)
```

System prompt 里显式引导模型遇到不确定时优先 zoom,而不是低置信度乱点 — 把"自愈"行为前置到决策阶段。

#### 2.4 Hybrid Grounding · Electron CDP 客户端 — `cua_lark/cdp.py`

飞书桌面端基于 Electron,启动加 `--remote-debugging-port=9222` 即可暴露 Chrome DevTools Protocol。我们用一个轻量同步 websocket 客户端做**只读 DOM 查询**,作为视觉断言的精确互校通道。

```python
class CDPSession:
    def evaluate(self, expression, return_by_value=True):
        result = self.send("Runtime.evaluate", {
            "expression": expression,
            "returnByValue": return_by_value,
            "awaitPromise": True,
        })
        return result.get("result", {}).get("value")

    def query_selector_text(self, selector):
        return self.evaluate(
            f"document.querySelector({json.dumps(selector)})?.innerText ?? null"
        )
```

**关键设计:CDP 只读不写。** 所有点击/输入仍走 OS 事件,确保测试反映"真实用户"语义,不被 DOM 注入捷径绕过。

#### 2.5 Testing-DSL — `cua_lark/dsl.py` + 真实用例

```python
@cua_test("IM · type a message in the first chat without sending", "im")
def test_im_type_message(ctx):
    ctx.do("Bring Feishu to the foreground")
    ctx.do("Click the Messages / IM tab in the left sidebar")
    ctx.do("Open the first conversation by clicking it")
    ctx.do("Click the message input box at the bottom")
    ctx.do("Type 'hello from CUA-Lark', do NOT press Enter")
    ctx.assert_visible(
        "the text 'hello from CUA-Lark' is visible in the message input box"
    )
```

5 行自然语言 + 1 行语义断言 = 一条完整 E2E 测试。**对照传统 Playwright/Appium 实现需要 30+ 行代码 + 易碎的 selector,代码体积下降 ~10 倍,UI 改版鲁棒性提升一个量级。**

#### 2.6 双通道断言 — `cua_lark/verifier.py`

```python
class VlmVerifier:                         # 视觉语义通道
    def assert_visible(self, claim):
        # 严格 JSON 输出:{"passed": bool, "reason": str}
        ...

class CdpVerifier:                          # DOM 精确通道
    def assert_text(self, selector, contains):
        actual = self.session.query_selector_text(selector) or ""
        return AssertionResult(
            passed=contains in actual, channel="cdp",
            detail=f"actual: {actual[:120]!r}",
        )
```

DSL 自动按"成本最低 → 信息最充分"路由:简单视觉判断走 VLM,需要精确文本/属性的断言走 CDP。**两通道还可互校,作为 Self-Heal 与误报检测的基础。**

### 3. 项目亮点介绍

#### 三张差异化拳头

| | 别人怎么做 | CUA-Lark 怎么做 | 价值 |
|---|---|---|---|
| **Testing-DSL** | 用 Computer Use 跑通用任务 demo | `@cua_test` 装饰器 + `assert_*` API,把 CUA 改造为 **QA 框架** | 测试用例从代码资产 → 自然语言资产,降本 10×,改版鲁棒 |
| **Hybrid Grounding** | 纯视觉(脆弱)或纯 selector(脆弱) | 视觉决策 + CDP 结构化断言,**两通道互校** | 视觉负责"做",CDP 负责"判",各取所长 |
| **Self-Heal via zoom** | 出错时人工干预 | 接入 Sonnet 4.6 独占的 `zoom`,**模型自主重定位小元素** | 跨 UI 改版自动适配,减少维护成本 |

#### 工程闭环(M1→M5 共 8 周路线)

| 里程碑 | 内容 | 完成度 |
|---|---|---|
| **M1** | 截图→Claude→单步操作闭环 | ✅ 已完成 |
| **M2** | DSL + CDP + Verifier + 3 条 IM 用例 | ✅ 代码完成 |
| **M3** | Docs + Calendar 子产品扩展 | 🟡 框架就绪,等用例 |
| **M4** | HTML 报告 + 评估指标 | 🟢 报告生成器已落地 |
| **M5** | Self-Heal + 跨产品联动 | 🟢 zoom 自愈已落地 |

#### 可推广性

- **Electron 桌面应用通用方案**:VS Code、Obsidian、Notion、Slack、Discord、Element 等均基于 Electron,加 `--remote-debugging-port` 即可复用全部 CDP 通道;DSL 与产品解耦,迁移成本极低。
- **企业内部 QA 流水线**:每条测试自动生成 `test_report.json` + HTML 可视化报告,可直接接入 CI/CD;失败定位天然包含截图轨迹与模型自述。

### 4. AI 亮点介绍

#### 高阶 AI 技巧

1. **最新工具协议**:`computer_20251124` + `computer-use-2025-11-24` beta header(Sonnet 4.6 / Opus 4.6+ 专用),抢先用上 `zoom` 等新动作。
2. **严格 JSON 验证模式**:Verifier 用强约束 system prompt 输出 `{"passed": bool, "reason": str}`,自带容错解析(支持 ```代码块包裹),避免自然语言断言的歧义。
3. **完整消息历史复用**:`tool_use` ↔ `tool_result` 全量保留,模型在 N 步操作后仍能引用第 1 步看到的内容,**比"每步独立调用"的常见错误实现高效得多**(token 摊薄、推理连贯)。
4. **`enable_zoom: true`**:把 Self-Heal 从"出错重试"前置到"决策时主动 zoom",降低无效操作导致的副作用。
5. **VLM × CDP 双通道互校**:同一断言可同时跑视觉与 DOM,二者一致才认为通过 — 误报率下降的同时也是 Self-Heal 信号源。
6. **Retina-aware 坐标系**:macOS 物理像素 ≠ 逻辑像素,Executor 通过 `scale = claude_w / logical_w` 统一坐标空间,模型与 OS 不再"鸡同鸭讲"。

#### 模型选型思路

| 角色 | 选型 | 原因 |
|---|---|---|
| **规划 + 执行** | Claude Sonnet 4.6 Computer Use | 原生返回屏幕坐标,无需额外 grounding 模型;`zoom` 原语支持 Self-Heal;OSWorld 70+ SOTA |
| **断言验证** | 同上 | 复用同一 client 减少冷启动;严格 JSON system prompt 控制输出 |
| **本地基线对比(M5)** | UI-TARS 7B | 离线/对比实验,验证云端 vs 本地的鲁棒性差异 |

**为什么不 fork UI-TARS-desktop?** 后者是 TS/Electron,Python 生态对 ML / VLM 调用更顺手;独立架构留出 DSL、Hybrid Grounding、Self-Heal 三个差异点的发挥空间;评委更看重原创架构。

#### 人机分工

| 人负责 | AI 负责 |
|---|---|
| 写测试意图(自然语言) | 看屏幕、决策、执行 OS 操作 |
| 提供前置条件(飞书已登录、调试端口已开) | 自我评估并 zoom 自愈 |
| 审核失败用例 | 双通道断言 + 写自述报告 |
| 维护 DSL 框架 | 适配 UI 改版(无需改测试代码) |

#### 引入 AI 后的工作流改变

| 维度 | 传统 GUI 自动化(Playwright/Appium) | CUA-Lark |
|---|---|---|
| 用例代码量 | 30+ 行 / 用例 | 5–8 行自然语言 |
| UI 改版鲁棒性 | selector 失效即批量崩 | 视觉语义理解,改版自适应 |
| 失败定位 | stack trace 反查 | 截图轨迹 + 模型自述,直观可视 |
| 跨产品复用 | 重写 selector | DSL 与产品解耦,迁移即用 |
| 维护成本 | 高(每次改版需重写 selector) | 低(zoom 自愈 + DSL 不变) |

### 5. 其他信息补充

- **完整 8 周路线图**:`docs/ROADMAP.md`
- **架构设计与选型论证**:`docs/DESIGN.md`
- **示例与用例**:`examples/hello_feishu.py` + `tests/feishu/im/im_basic.py`
- **运行报告样例**:`runs/<timestamp>/report.html`(自包含 HTML,内嵌截图,无外链)
- **不依赖任何 fork**:从零自研 1500+ 行 Python,UI-TARS-desktop 仅在 DESIGN.md 中作为对标引用。

---

## 三、其他信息(自由发挥区)

### 研究背景与延伸

我目前的研究方向集中在**大模型后训练**(post-training)与**长上下文优化**(self-anchored DPO 等),年底将有 2A + 1B 在投 / 接收。CUA-Lark 是我对**"如何把视觉 LLM 工程化为可靠 QA agent"**的一次系统化实验:

- 它验证了 Sonnet 4.6 的 `zoom` 原语作为 Self-Heal 一阶机制的可行性 —  这是相对于 Sonnet 4.5 / Haiku 4.5 的代际升级,值得作为后训练数据策略的参考。
- 它把"视觉决策 + 结构化断言"做成了可工程落地的工作流,而不是 demo 级别的 agent loop。这套范式可直接迁移到字节内部 QA 工具链。

### 未来工作

如果有机会延展为长期项目,可以推进的三个方向:

1. **跨产品智能联动测试**:IM 收到日历邀请 → 自动跳转日历确认 → 返回 IM 校验状态 — 把 CUA 升级为多产品流水线。
2. **Self-Heal 自动数据采集**:每一次模型 zoom 重试都是"被动学习样本",可回流到模型微调,持续提升 Self-Heal 命中率(数据飞轮)。
3. **企业 QA SaaS 化**:把 CUA-Lark 抽象为云服务,用户上传 Electron app 即可生成自动化测试,DSL 用例则由内部 LLM 从产品文档中自动合成。

### 联系方式

- GitHub:[ANTI-Tony](https://github.com/ANTI-Tony)
- 项目仓库:https://github.com/ANTI-Tony/lark_c
- 邮箱:jwen2914@uni.sydney.edu.au

期待与飞书 ByteIntern 团队合作。
