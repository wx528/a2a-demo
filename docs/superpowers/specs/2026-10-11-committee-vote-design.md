# V1 委员会独立投票（Committee Vote）设计

- 日期：2026-10-11
- 状态：已与用户对齐设计（A′：门开前对方向投票），待评审
- 前置：弹性专家席位已上线（guest-experts 已合并）；本文为 v1 范围

## 1. 背景与动机

当前 V2 流程中，决策门的依据是定性讨论 + 单点综合建议——多智能体辩论的已知缺陷
（后发言者向先发言者/自信者收敛、互相说服而非逼近真相）会在门前讨论里集中体现。
独立投票（self-consistency 式集成）是被验证的去偏机制：各席位在**看不到彼此动向**的
前提下，对「当前讨论方向」独立给出定量评价，为决策门提供量化信号（门旁计票），
也为 demo 增加"开票"的表现力。

流程事实：门开于 review 末（Linus 挑战后）、Sage 综合在门后。故 v1 投票标的是
「当前讨论方向」，不是（尚不存在的）Sage 建议。

v2 远期愿景（匿名提案→盲投）不在本期。

## 2. 目标 / 非目标

**目标**
- review 末（challenge 发言完成）、决策门打开前，全部 4 个席位（含 Sage）独立投票
- 票型匿名：收齐前不发布任何票；逐票明细永不落 turns / 快照 / 导出
- 计票结果消费于三处：讨论流（vote_summary turn）、决策门旁（计票条+理由）、outcome/export
- demo 模式有确定性脚本票；真实模式每任务 +4 次 LLM 调用（可接受）

**非目标**
- 不做匿名提案与盲投（v2）
- 投票结果**不改变流程**（全票反对也照常开门，判断权留给用户）
- 不做逐维度打分收集（rubric 只做 prompt 引导）
- 不承诺"绝对匿名"（文风可被识别，产品文案写"匿名（尽力）"级别即可，不刻意宣传）

## 3. 选票格式与评判标准

```json
{"verdict": "approve | adjust | reject", "confidence": 1, "reason": "≤60字"}
```

- 投票标的：「是否认可当前讨论方向（可推进到建议整理阶段）」
- `confidence`：1-5 整数，对自评的把握
- rubric（写入投票 prompt，不收集逐项分）：与已确认约束的一致性 / 可行性 / 未被讨论的风险
- 输出约定为严格 JSON；解析失败重试 1 次；仍失败记 `abstain`（不阻塞开票）

投票 prompt 内容（每个席位独立调用，互不可见）：
目标 + 已确认约束 + 讨论纪要（截至当前的全体发言，含署名——讨论本来就是公开的）
+ rubric + 输出格式要求。
**不含**：任何其他席位的当前票、票向或提案。
（独立性指"不知他人当前票"，非"无知之幕"。）

## 4. 流程时序与事件

```
... review_linus turn_done
→ vote_start            {author: "committee"}            // 前端显示「委员会投票中…」
→ （编排器逐席位内部调用；不发布 turn_delta，票是 JSON 不流式）
→ vote_revealed         {turn_id, tally, split}          // 一次性开票
→ vote_summary turn 落盘（kind="vote_summary", author="committee"）
→ decision_required（既有决策门，问题/选项按既有逻辑；门旁显示计票）
```

- 挂点：review 阶段发言计满、`_open_gate` 之前；全任务仅投一次（`committee_vote` 已存在即跳过）
- 「暂不确定」路径重开的第二轮门：门旁复用同一份 `committee_vote`（标注「首轮投票」），不重投
- `split` 判定：`unanimous`（全票同向）/ `majority`（有 2+ 同向且有异议）/ `split`（无多数）
- 弃权票计入 `ballots` 但 verdict 为 `abstain`，不计入 tally 分子

## 5. 匿名机制（关键不变量）

- 收齐前零发布：任何 SSE 事件、DB 写入都不得包含单票内容
- 开票后合成**单个 turn**（`vote_summary`），body = 固定 seed 洗牌后的匿名票
  （展示名「评审 1..N」）+ 计票摘要；`author="committee"`
- **逐票明细不落任何持久层**：turns、V2Task 快照、outcome.evidence、export 一律只有
  汇总与匿名列表 → 匿名在数据层成立，不依赖前端遮罩
- 洗牌用 `random.Random(task.id)`，保证重放/测试确定性

## 6. 数据模型

```python
class Ballot(BaseModel):
    verdict: Literal["approve", "adjust", "reject", "abstain"]
    confidence: int = 0          # abstain 时为 0
    reason: str = ""

class CommitteeVote(BaseModel):
    tally: dict[str, int]        # {"approve": n, "adjust": n, "reject": n}
    split: Literal["unanimous", "majority", "split"]
    ballots: list[Ballot]        # 洗牌后固定顺序（匿名）
    quorum: int                  # 实际成票数（非 abstain）

class V2Task(...):
    committee_vote: CommitteeVote | None = None   # 可选字段，旧任务 None 零迁移
```

`vote_summary` turn：`title="委员会投票"`，body 为渲染好的匿名票文本（与展示一致），
evidence 不引用票（票不是发言）。

## 7. 投票调用实现（agents_client 扩展）

- 新增 `vote_direction(task, seat) -> Ballot`：复用 `speak` 的 URL 解析
  （快照优先→ROLE_AGENTS 回退）与 A2A 流式通道，但**聚合后再解析 JSON**（不逐 delta 发布）
- prompt 构造复用 `build_turn_prompt` 的骨架：身份行（builtin 人设/特邀专家职责）+ 投票指令
- 解析：抽取首个 JSON 对象（容忍 ```json 围栏）；重试 1 次；失败 → Ballot(verdict="abstain")
- ThinkFilter 照常应用（think 块不进解析）
- guest 席位天然参与投票（走同一接口）；demo 任务不发起真实调用

## 8. demo 模式脚本

固定票（与 goal 无关，确定性）：

| 席位 | verdict | confidence | reason（方向） |
|---|---|---|---|
| ada | approve | 4 | 方向与已确认约束一致 |
| turing | adjust | 3 | 建议补一个可观测的验收口径 |
| linus | reject | 2 | 试点边界外仍有未讨论的权限面 |
| sage | approve | 4 | 各阶段证据无根本分歧 |

→ 2:1:1（majority），tally/split 逻辑与真实模式同代码路径。

## 9. 前端消费

- **MeetingPod**：`vote_start` → 讨论区尾部「委员会投票中…」指示（复用思考指示器机制）
- **讨论流**：`vote_summary` turn 用专属渲染（计票条 + 匿名票卡逐条 fade-in），时间线常驻
- **DecisionGate**：门卡片旁显示 mini 计票条（approve/adjust/reject 三段横条）+ split 徽标
  （第二轮门标注「首轮投票」）
- **OutcomePage/OutcomeOverview**：`committee_vote` 区块（计票 + split）
- **export**：新增「委员会投票」一节（匿名票文本同 turn body）

## 10. 失败与边界

- 单票失败→重试→弃权；**全部弃权**→不生成 committee_vote、不发 vote_summary，直接开门
  （流程永不因投票阻塞）
- 投票期间用户无门可确认（门在投票后才开），无 confirm 竞态；投票全程状态仍为 running，
  pause/resume/retry 语义不变（投票属 review 末的一个推进单元，位于 `_step` 内）
- 旧任务（无字段）：`committee_vote=None` 全链路空值安全；重试/恢复不重投（有 vote_summary 即跳过）
- 多轮决策：仅首轮门开前投票一次

## 11. 测试计划

- 单元：JSON 解析（围栏/前后噪声）、重试、弃权、split 判定、洗牌确定性（同 id 同序）
- lifecycle：review 末 → vote_summary → gate 时序；全弃权跳过；旧任务空值安全；不重投
- API/SSE：事件序 `vote_start → vote_revealed → decision_required`；REST 快照含 committee_vote
- demo：脚本票 2:1:1、export 含投票节
- 回归：既有 155 项全绿；ruff / lint / build

## 12. 工程拆分预估

1. 模型 + 解析/聚合纯函数（Ballot/CommitteeVote/parse/split/shuffle）
2. agents_client.vote_direction + 编排器挂点（`_step` review 末、门开前）
3. demo 脚本票
4. 前端：投票指示 + vote_summary 渲染 + 门旁计票条
5. outcome/export 集成
6. 测试补齐 + 全量回归

预计与 guest-experts 相当或略小（无注册表面）。
