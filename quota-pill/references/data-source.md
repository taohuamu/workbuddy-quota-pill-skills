# 数据来源与字段

> 上次核对：2026-11-20（数值会随使用变化，模型清单也可能增减，按文末命令重新核对）

## 数据从哪来

WorkBuddy 每轮请求都会在本地会话日志里写一行，其中 `providerData.rawUsage.quota` 是该轮服务端下发的配额快照。路径：

```
%USERPROFILE%\.workbuddy\projects\<项目>\<会话>.jsonl
```

国际版可能在 `~/.workbuddy-ai`；环境变量 `WORKBUDDY_HOME` 可覆盖根目录。本技能只读这些文件。

## 字段

| 字段 | 含义 | 注意 |
|---|---|---|
| `quota.model` | 配额池名称 | 与 `providerData.model` 可能不同名，对外展示用这个 |
| `quota.percent` | 已用百分比 | 整数，粒度 1%，服务端原值 |
| `quota.reset_at` | 下一次重置时刻 | **字符串形式的 Unix 秒**（如 `"1794436218"`），需先转数值 |
| `quota.shared_models` | 共用同一配额的模型 | 通常为空数组 |
| `rawUsage.credit` | 该轮消耗的积分 | 与配额是两套计量，本技能不展示 |

## 字段覆盖率（2026-11-20 实测，会变）

**分母是「带 `rawUsage` 的记录」，不是全部日志行。** 同一段对话会写很多不带 `rawUsage` 的行，
拿全部行数作分母会把 67% 算成 22%，据此判断「字段很稀疏」就错了。

| `providerData.model` | `quota.model` | 带 quota / 带 usage | 说明 |
|---|---|---|---:|---|
| `deepseek-v4.1-flash` | 同名 | 5729 / 8556（约 67%） | 更新最及时，基本每轮都带 |
| `hy4-free` | `hy4` | 154 / 1441（约 11%） | 数字可能长时间停住，属正常 |
| `hy4-flash-free` | `hy4-flash` | 17 / 373（约 5%） | 与 `hy4-free` 是两个模型、两个配额池，别合并 |
| `glm-5.3-flash` | — | 0 / 729 | 未见下发，按积分计费 |
| `deepseek-v4-pro` | — | 0 / 425 | 记录集中在配额字段上线之前 |
| `hy3` | `hy3` | 2 / 35 | 偶发 |
| `glm-5.3` | 同名 | 1 / 2 | 有配额——与 5.3-flash 不同，别按系列一刀切 |
| `kimi-k3-1` | `kimi-k3` | 3 / 3 | 次数少但都带 |
| `kimi-k3.1-pro` | 同名 | 3 / 3 | 同上 |
| `step-5-preview` | 同名 | 1 / 1 | 单次调用，带 |
| `mimo-v2.6-pro`、`glm-5.2`、`space-bunny`、`minimax-m3.1-flash`、`kimi-k2.8-preview`、`hy4free` | — | 0 | 有调用记录，服务端一律没下发 quota。`hy4free` 与 `hy4-free`、`hy4-flash-free` 是三个不同的 `providerData.model` |

同一模型出现在两处时以 `quota.model` 为准。**这张表不要背下来**，每次回答以脚本输出为准。

## 表里那两列是怎么来的

`quota.percent` 是服务端原值，直接透传；「近 15 分钟」「按此速度」是本地算出来的，两者性质不同：

| 列 | 怎么算 | 能断言什么 |
|---|---|---|
| 近 15 分钟 | 最近 15 分钟内每一次**正向**跳变累加，回退记 0 | 观测事实：这段时间涨了几个百分点 |
| 按此速度 | 用上面那个涨幅估等待时间的**中位数**（`T/(T+W) ~ Beta(R, k+½)`） | 条件句：**按当前速度**还要多久；用户停手就不兑现 |

回答时的两条边界：

- 「按此速度」是「—」有三种情况，别混成一句：最近 15 分钟没涨（显示 `涨 0%` + `—`）、
  距重置不足一个窗口（`即将重置`）、这一行根本没有快照。
- `涨 0%` 只说明窗口内没观测到新增，**不等于不会用完**。百分比本身还在，只是停住了。

## 核对命令

两件事要分开核对。只看报告会漏掉「有调用记录但没配额」的模型，而上面那张表里一半是这类。

**一、本周期有哪些模型有配额**（报告口径）

```bash
python "${CODEBUDDY_SKILL_DIR}/scripts/quota_report.py" --no-cache
```

**二、日志里一共出现过哪些模型**（含没有配额的）

```python
# 存成 cov.py 运行：统计每个 providerData.model 出现过多少次
import collections, glob, json, os

root = os.path.expanduser("~/.workbuddy/projects")
counter = collections.Counter()
for path in glob.glob(os.path.join(root, "*", "*.jsonl")):
    for line in open(path, encoding="utf-8", errors="ignore"):
        if not line.strip():
            continue
        try:
            pd = json.loads(line).get("providerData") or {}
        except ValueError:
            continue
        if pd.get("model"):
            counter[pd["model"]] += 1
for model, n in counter.most_common():
    print("%-24s %d" % (model, n))
```

- 第一条里有、表里没有的模型 → 新配额池，补进表并改「上次核对」日期。
- 第二条里有、第一条里没有的 → 有调用但没下发 quota，补进表的 0% 区。
  只跑第一条永远发现不了这一类，这是上一版核对方法漏掉的部分。

## 已知缺失

- 账号积分余额、积分包到期：需要登录态查 billing 接口，不在本地日志里。
- 未使用过的模型、服务端未下发 `quota` 的模型：不会出现在结果中。
- 百分比只有整数位，1% 以内的变化看不出来。
