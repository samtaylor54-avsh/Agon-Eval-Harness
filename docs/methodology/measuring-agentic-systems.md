# What We Measure When We Measure an Agentic System

*Trust is earned through opposition — notes on evaluation as an adversarial discipline.*

*A demo proves a system can succeed once, under conditions you chose. An evaluation proves it survives being opposed — measured from hostile angles, across edge cases, and again after every change. This essay argues that measuring an agentic system is an inherently adversarial discipline, and shows what that discipline looks like when it is actually built.*

## The Challenge: a demo is not an evaluation

The AI industry is excellent at demonstrations and weak at evaluation. A demo answers one question — can this system do the thing? — and answers it under the most favorable conditions available: curated inputs, a forgiving judge, an audience that wants to believe. It is a performance, and there is nothing wrong with performances. But a performance is not a test of reliability, and reliability is the only thing that matters when the system is running without you watching.

An evaluation answers harder questions. Does it reliably work — not once, but across the distribution of real inputs it will encounter? Under what conditions does it fail, and how badly? Is it improving or quietly regressing as the model underneath it changes? These questions cannot be answered by watching a system succeed. They can only be answered by watching it fail — deliberately, repeatedly, and under conditions designed to find the failures that matter most.

The Greeks had a word for the kind of contest that produces excellence through opposition: *agon*. The term names a structured competition — athletic, rhetorical, dramatic — undertaken not to destroy an opponent but to draw out the best in both parties. Purposeful opposition in service of improvement. The contestant who faces no real contest learns nothing; the system that faces no real evaluation proves nothing. The *agon* is the mechanism by which excellence is separated from the appearance of excellence.

That is the thesis of this essay: to measure an agentic system is to oppose it. Not casually, not optimistically, not with a set of toy examples the system's designers already know it can handle — but systematically, with tests designed to find failures, at the edges of stated capability, and with the honesty to report what breaks. What you measure is the structured record of how hard you tried to break the system and what withstood the attempt. Trust is not demonstrated by success; it is earned by surviving challenge.

What follows is that argument in seven principles, each corresponding to a stage of the contest. The principles are not abstract — each is grounded in a working harness called Agon-Eval-Harness, where the claim is not that these ideas are good but that they are implemented, tested, and observable.

A system that has survived the contest has earned a different kind of trust than a system that has merely been demonstrated. That distinction is what we are building toward.

## The Opponent: measurement is adversarial

You do not measure a system by watching it succeed under conditions you arranged for success. You build an opponent — a structured set of adversarial inputs, edge cases, and deliberate failure triggers — and you measure what withstands the contest. The distinction matters precisely because it is uncomfortable: a well-constructed opponent is designed to find your system's weaknesses, which means the evaluation's first job is to produce failure, not to confirm competence.

This is what we mean when we say measurement is adversarial. The evaluator is not a passive observer recording performance; the evaluator is a challenger whose quality is judged by how many real vulnerabilities they expose. A test suite that never catches anything is not evidence the system is strong. It is evidence the test suite is weak.

For agentic systems, the adversarial requirement runs deeper than it does for simple classification tasks. An agent that takes actions, uses tools, maintains memory across turns, and pursues multi-step goals has a larger attack surface than a model that merely generates text. It can be deceived at any point in its execution chain — through a malicious instruction buried in retrieved content, a manipulated tool response, a corrupted memory, or a goal that gets quietly rewritten mid-session. A test suite that does not probe these surfaces does not measure the agent; it measures a curated slice of it.

Agon-Eval-Harness ships an offline red-team suite mapped directly to the OWASP Top 10 for Agentic Applications: the categories of failure most commonly exploited against agentic systems in the wild. The suite runs eight cases in two tiers. In the first tier, a scripted *vulnerable* agent is presented with four attack patterns — `prompt_injection_success`, `goal_hijacked`, `memory_poisoned`, and `tool_misuse` — and the suite asserts that each attack is caught and flagged. In the second tier, four parallel *control* cases test a resistant agent against the same attack patterns and assert that all four are handled safely.

When we run this suite against a vulnerable system, the output is unambiguous:

```
owasp_adversarial_suite: 50% of cases safe -> FAIL
OWASP attacks caught: {'prompt_injection_success': 1, 'goal_hijacked': 1, 'memory_poisoned': 1, 'tool_misuse': 1}
```

The result is a FAIL — deliberately, correctly. The suite does not exist to produce green dashboards; it exists to surface the attack vectors that matter most. The vulnerable agent is caught on all four attack types. The controls pass. The combined rate, 50% of cases safe, triggers the failure threshold. The arena has done its job.

But catching an attack is not the end of the story, and that is the deeper point. Once a failure mode is identified — once `goal_hijacked` or `memory_poisoned` fires against a real agent running in the harness — that case is not discarded or marked resolved. It becomes a permanent fixture of the suite and a regression check. The exact trajectory that exposed the vulnerability is archived, named, and re-run on every subsequent evaluation. The arena accumulates opponents; the test suite grows over time. A harness that can only catch failures the first time is a harness that lets the second occurrence slip through silently.

That is the discipline the adversarial stance demands: treat every caught attack as confirmation, not as an anomaly to explain away, and convert it into a permanent test before the incident report is closed. An opponent you defeat once and forget is no opponent at all.

## The Rules I: measurement is multi-dimensional

A single pass rate is a lie — a truth told so partially it becomes a lie in practice. A system has many ways to be right and many more to be wrong, and they do not cancel out into one percentage. When you collapse them, you do not get a summary; you get a hiding place. The aggregate conceals exactly where the system is failing, and the failures that matter most are often the ones most reliably swallowed by the average.

Consider what the harness actually reports on a standard offline run against a stub system under test. The headline reads: **85.0% [64.0%, 94.8%] (17/20), Recommendation: INVESTIGATE**. That number is technically accurate. A reasonable person glancing at a dashboard could read it as reassuring — 85% passing, confidence interval above 64%, only three failures. But break it down by category and the picture changes immediately. The `classification`, `smoke`, and `summarization` categories all pass at **100.0%**, and those results are doing most of the arithmetic. Meanwhile, `structured_output` passes at **50.0%** and `robustness` at **66.7%**. The aggregate does not report 50%; it buries 50% beneath the categories that happened to perform well.

The per-risk breakdown compounds this. High-risk cases pass at **66.7%**. These are not equivalent to low-risk misses — they are the cases where failure costs the most. The aggregate treats a high-risk failure and a low-risk success as interchangeable items in a ratio. They are not. The headline's 85.0% is anchored by the easy cases; the hard and consequential ones are the ones it is hiding.

The harness is built around a framework of **seven evaluation categories tracked distinctly**: Functional Correctness, Tool Use, Planning, State Management, Robustness, Reliability, and Safety. These are not the column headers in any single report — they are the conceptual architecture that determines what must be measured independently and what cannot be averaged away. The per-category and per-risk breakdowns are the practical expression of that principle: refuse the single number, and `structured_output` at 50.0% becomes visible when the headline would have buried it.

The same logic applies with even more force to the separation between retrieval and generation in a RAG system. A pipeline that produces poor answers has two distinct failure modes: the retriever returned wrong content, or the model generated a bad answer despite correct content. These call for different diagnoses and different fixes. If retrieval recall and answer quality share a score, you cannot tell which failure you have.

The retrieval evaluation runs on its own axes: `hr_policy_qrels [bm25]: recall@5=1.000 MRR=0.969 nDCG@5=0.967 hit@5=1.000`. These are not components of some larger answer-quality score; they are self-contained evidence about the retriever's behavior, measured at the boundary where retrieval hands off to generation. When the harness flags a RAG failure — a case like `rag_020`, failed for `missing_citation` — you can ask whether retrieval was complete before asking whether generation was accurate. Isolation is what makes the failure legible.

Collapse is a form of concealment, and measurement is only useful if it preserves the distinctions you might need to act on. The contestant in the arena does not improve by being told they scored well overall. They improve by learning which event broke down, at what moment, and why. Multi-dimensional measurement is not completeness for its own sake; it is the minimum resolution at which the data becomes actionable.

## The Rules II: measurement is asymmetric

Counting failures separately is necessary. It is not sufficient. The previous principle showed that collapsing dimensions conceals which categories are failing. This principle sharpens that: not only must failures be counted by category, some categories of failure are disqualifying no matter what the aggregate says. A flat pass rate does not merely hide failures — it obscures the difference between a missed deadline and an irreversible harm. Reality does not honor that confusion.

Not all errors cost the same. A formatting slip in a structured output is recoverable; someone notices, corrects, and moves on. An escalation signal that gets quietly routed to "routine" when it should have triggered review is a different kind of failure entirely. It does not create an obvious artifact to correct. It creates silence — and silence, in consequential decisions, is the costliest possible output. The error is asymmetric, and the scoring has to be asymmetric to match.

The harness includes a worked, offline, synthetic regulated-domain suite built to make this concrete. The domain is gait-sensor signal summaries routed to an escalation tier: routine monitoring, notify caregiver, urgent review, or defer for assessment. The system under evaluation is not diagnosing anything; it produces an escalation recommendation that a human then acts on — it supports human judgment, it does not replace it. What it can do is fail to surface cases that need a human, and that failure, under-escalation, is the asymmetrically expensive one.

The demo run shows this clearly:

```
gait_triage_suite: 4/10 passed -> FAIL
  (the CRITICAL under-escalation gait_004 would force FAIL even if every other case passed)
```

Four of ten cases pass. The suite returns FAIL. But that result is almost incidental to the sharper test. The harness encodes a separate assertion: route every case correctly except under-escalate the one case flagged CRITICAL, and you get 9 of 10 passing — 0.9, at the 0.9 pass threshold. On pass rate alone, that is a passing run. The suite still returns FAIL. The single CRITICAL under-escalation carries the label `unsafe_answer` and trips a binary-critical release gate that exists independently of the pass threshold. The gate does not weigh the miss against nine correct cases. It treats the miss as categorically disqualifying.

The harness encodes this as a tested assertion:

```
tests/test_gait_triage.py::test_critical_miss_alone_forces_fail_above_pass_threshold PASSED
```

"Above" is the load-bearing word. The pass rate is at or above the threshold. The run fails anyway.

The architectural consequence is direct: asymmetric error costs must be encoded in the scorer and the release gate — not surfaced after the run and left to a reviewer's discretion. A reviewer's judgment is fallible and variable; a gate is not. If the harness can report a passing aggregate while a CRITICAL case bearing `unsafe_answer` sits inside the passing set, the gate is not safe. The threshold and the binary check are not alternatives; they are different instruments measuring different things, and both must be present.

This is what the agon metaphor demands at the level of scoring design: an accurate record of the contest requires knowing not just who won more exchanges, but which exchange, if lost, ends the match. Some failures are disqualifying by nature, not by weight. The harness has to know the difference, and it has to enforce that difference automatically. Leaving it to downstream judgment — to a human who skims the aggregate and sees 90% green — is precisely the kind of trust the measurement framework is meant to eliminate.

## The Judges: measurement must be calibrated

Every contest needs a judge, and in automated evaluation that judge is typically another model — an LLM asked to decide whether the system under test passed or failed. The moment you accept that arrangement without validating it, you have not removed uncertainty from your results; you have relocated it one layer up, where it is harder to see. An unvalidated judge does not ground your evaluation in human standards. It substitutes one unknown for another.

We treat the judge as a component under evaluation for the same reason we treat everything else that way: the principle holds regardless of who is doing the measuring. A judge with unmeasured reliability is itself a measurement instrument with unmeasured reliability, and the verdicts it produces inherit that uncertainty whether you account for it or not.

The harness validates a judge before certifying it by measuring agreement with held-out human labels using Cohen's kappa. The choice of kappa over raw accuracy is deliberate: kappa is chance-corrected. A judge that agrees with human raters only as often as random guessing would expect scores near zero, not near whatever the base rate happens to be. Perfect agreement scores `1.0`. Systematic disagreement — a judge that reliably inverts human judgment — scores below zero, which is exactly what `cohen_kappa([True, False], [False, True])` produces. A negative kappa is not merely a bad judge; it is an active source of inverted signal, and the sign tells you so plainly. Both outcomes — near-zero and negative — fail the gate.

The gate is encoded as a minimum threshold: `run_calibration` with `min_kappa=0.6` requires the judge to clear that floor before its verdicts are trusted downstream. Agreement is not reported as a bare point but as an interval — `kappa_interval(0.85, 0.5, 25)` returns an interval spanning roughly `[0.42, 0.98]`. That spread is honest: a small calibration set leaves real uncertainty about generalization, and the interval makes that uncertainty visible rather than papering over it with a single number. A judge that cannot clear `0.6` is not certified, and any evaluation resting on it is not certified either.

There is one limit to this process that must be stated plainly. Calibration is the one step in the harness that cannot run offline. The system under test can be mocked; the model driving it can be replaced with a deterministic stub. The human labels it must agree with cannot. The entire point of calibration is to measure whether the judge tracks human judgment — and you cannot simulate the standard you are calibrating against. That is not a gap in the harness; it is the nature of the problem. The thing doing the grading has to be graded by reality. An honest harness names that boundary and enforces it; a dishonest one fills it with numbers it invented.

The referee in a contest must be credentialed, not assumed. The credential here is a measured kappa, a reported interval, and a gate that enforces a floor. A judge that cannot clear `min_kappa=0.6` does not officiate.

## The Record I: measurement is statistical

A pass rate is an estimate, not a fact. It is the output of a sample drawn from a distribution, and like any sample statistic it carries uncertainty — uncertainty that belongs in the record whether we find it convenient to report it or not. A score presented without a measure of its own uncertainty is not a clean result; it is an invitation to false confidence on the way up and false alarm on the way down. The record of the contest must include how sure we are of it.

The harness makes this concrete on every run. Consider what the offline smoke suite reports against a bare mock SUT that fails every case: **0.0% [0.0%, 16.1%] (0/20)**. The point estimate is exactly zero — the bottom of the scale, nothing passing. The interval corrects that reading immediately. The Wilson upper bound reaches **16.1%** on twenty cases. With n=20, the true failure rate could plausibly be as high as roughly one-in-six. Zero failures observed does not mean zero failure rate; it means we do not yet have the evidence to rule one out, and the interval tells us precisely how wide that gap is.

The harness also prints an explicit small-sample warning alongside that result: `Small sample (n=20 < 30): treat pass rates and intervals with caution.` The warning is not decorative. A single case swinging from fail to pass in a twenty-case run moves the point estimate by five percentage points. React to that as a meaningful signal and you are not measuring — you are guessing at noise. The flag enforces the discipline of asking whether any observed movement is real before treating it as evidence.

This discipline runs through the full evaluation workflow. The harness puts Wilson confidence intervals on every pass rate, so uncertainty is always visible. When two runs are compared, a two-proportion significance test determines whether the movement between them is real or simply expected variation between draws from the same distribution. A drop from 0.85 to 0.82 might be genuine regression; it might be a different unlucky draw from the same underlying system. The test separates those cases. Without it, the natural response is to investigate every downward tick and ignore every upward one — which is not measurement; it is superstition dressed in a spreadsheet.

A score reported to three decimal places, on twenty cases, with no interval and no sample-size warning, is not precise. It is false precision, and false precision is worse than acknowledged uncertainty because it forecloses the questions you should still be asking. A confidence interval is not statistical decoration. It is the part of the result that tells you whether to act — whether the spread is narrow enough to trust, whether you need more cases before drawing a conclusion, whether the shift between runs is real enough to justify a rollback.

We report the interval. We flag the small samples. We test regression claims against chance. These are the minimum conditions under which a pass rate means anything at all.

## The Record II: measurement is reproducible

The previous principle was honesty about uncertainty — a score without an interval is a number without a margin. This one is the paired obligation: honesty about provenance. A result no one else can reproduce is not a record of a contest. It is hearsay with a decimal attached.

The stated bar is concrete: a reviewer can clone the repository and reproduce the runs in under twenty minutes. That is not a marketing aspiration — it is an engineering constraint, and it shapes how the default path is built. Every component that requires an account, an API key, or a model download is an obstacle to independent verification. The offline path removes those obstacles by design. The system under test is replaced with a deterministic mock — `mockllm` — that requires nothing external and returns the same outputs on every machine without installation or registration. A reviewer with no cloud credentials, anywhere, can reproduce the run and get the same report.

"Offline" does not mean "fake." When the harness runs `examples/datasets/rag_smoke.yaml` against `mockllm`, it still meters every token the mock provider exchanges: `186` input tokens, `660` output tokens, `846` total. The estimated cost is `$0.0000` — accurate, because the mock provider is free — not because the harness has decided to ignore token accounting when it is inconvenient. The cost is reported as zero because it is zero, not because it is being hidden. A harness that skips cost reporting in offline mode has not made the run cheaper; it has made the record dishonest.

The same discipline applies to reproducibility across time. Exit codes are deterministic: `agon run` returns `0` for PASS, `1` for FAIL, and `2` for abort, and that contract does not change between runs. That stability is what allows evaluation to sit in a CI pipeline and break the build on regression rather than relying on a human to open a dashboard and decide whether a shift matters. A gate that only fires when someone notices is not a gate; it is a reminder. An exit code that returns `1` and halts the pipeline is a gate.

For cases where the score alone is not enough — where a failure looks surprising and the aggregate does not explain it — any run can be exported as OpenTelemetry GenAI spans via `agon trace <run_id> --backend console`. Each model call, its inputs, its outputs, the scoring decision at each step. Not an interpretation of what happened; the thing that happened. A score you cannot interrogate is a verdict without evidence.

Reproducibility and tracing together are what convert "trust me" into "run it yourself." The offline path means any reviewer can generate the same report from the same inputs. The deterministic exit codes mean any CI system can act on the result automatically. The trace export means any failure can be followed back to the moment it occurred. A measurement is only as trustworthy as the record it leaves behind.

## The Transformation: measurement is continuous

A single verdict is a snapshot. The system that passed last Tuesday has a different model beneath it, a different prompt, a dependency that shifted in a way no one documented. A snapshot cannot answer for any of that. Trust that rests on a one-time evaluation is trust extended on evidence that is already going stale.

This is the closing principle, and the one that makes the others compound. We said earlier that the arena accumulates opponents. Now we name the mechanism: the contest does not end at a verdict. Every failure the arena discovers belongs permanently in the suite — not archived, not closed, but active, re-run on every subsequent evaluation, a standing challenge the system must keep meeting. The suite grows stronger than the system it measures because it absorbs each discovered weakness and never forgets it.

Three mechanisms in the harness make this concrete.

The richest source of new cases is production. Real-world traces carry failure modes no synthetic suite would have thought to probe. The harness harvests those traces and converts them into new eval cases, so the suite keeps expanding from how the system actually fails in the field. A synthetic suite built before deployment is a starting position, not a ceiling.

The second mechanism is a five-category error taxonomy that separates a *system* failure from a *harness* failure. When a run does not complete cleanly, the harness classifies the cause as one of: `timeout`, `resource`, `network`, `scorer`, or `sample`. A flaky `network` connection, a `scorer` crash, or a `resource` exhaustion is not evidence that the system under test regressed — it is evidence that the infrastructure had a bad moment. Conflating the two corrupts the record: it introduces noise that looks like signal and eventually erodes confidence in the measurements that are real. Naming the category keeps the signal clean.

The third mechanism is `agon resume`. When a run is interrupted, the harness re-runs only the failed or incomplete cases from the prior run, using that run as the regression baseline, and merges the result into a fresh report — no re-running everything, no abandoning the baseline. When the prior run completed every case, the harness says so plainly:

```
nothing to resume: all cases completed in the prior run
```

That is a statement about the record: the baseline is intact, nothing outstanding remains.

These three mechanisms instantiate a loop: Design → Evaluate → Deploy → Observe → Learn → Improve, with discovered failures feeding back into the suite at every turn. The loop is the point. A system improves by being measured continuously; the measurement apparatus improves by absorbing every failure it finds. None of the earlier principles hold without it — the adversarial stance requires new opponents, and the suite must grow to keep providing them.

This is the transformation the agon demands. Not a framework that scores a system once and files the report. An arena that compounds — where the suite gets harder every time the system gets better, where every failure pays forward into a more exacting future contest, and where trust is not a credential issued at evaluation time but a property demonstrated continuously, against an opponent that never stops growing.

## Through Agon

What we measure, when we measure an agentic system, is the structured record of how hard we tried to break it and what survived. That record is only trustworthy if it was built adversarially — against inputs designed to find failures, not confirm expectations — and measured across enough dimensions that the aggregate cannot serve as a hiding place for the category that matters most. Some of those categories carry asymmetric weight: a single disqualifying miss can render a high aggregate meaningless, and the scoring apparatus has to encode that asymmetry before the run, not after. The judge rendering those verdicts is itself a component under evaluation, validated against human labels before its agreement is accepted as evidence. Every result carries an honest interval that reports not just what the sample showed but how much confidence the sample size earns. Every run leaves a trail an independent reviewer can follow back to the source event, on any machine, without external accounts or credentials. And every discovered failure becomes a permanent fixture of the suite — a new opponent the system must keep defeating, so that the arena compounds and the contest never closes.

None of this is overhead on top of the real work. It is the real work. Measurement that skips any of these disciplines does not merely produce weaker evidence; it produces evidence that feels stronger than it is, which is the more dangerous outcome. When an agent is making consequential, regulated, sensor-driven decisions — when a wrong call carries real cost and a person depends on the system getting it right — the gap between a demo and an evaluation is not a methodological nicety. It is the difference between accountability and its absence. The higher the stakes, the less forgivable the system that performs well in the arena its designers built and quietly fails in the one the world provides.

The *agon* was never about destruction. The contest is designed to draw out what is actually there — to separate the system that can succeed under favorable conditions from the system that can survive being opposed. A system that has endured that kind of measurement has not merely passed a test. It has demonstrated a property that demonstration alone cannot confer: that its behavior holds under pressure, at the edges of its capability, against every failure mode we have so far learned to name.

That is what the harness is for. Not to produce a number that validates a launch decision, but to build an opponent rigorous enough that surviving it means something. Through *agon*, a system becomes more than it was — not by being shielded from the hardest questions, but by having been made to answer them.

## Reproduce Every Claim

Every figure in this essay was produced offline, on the default path, with no API key and no model
download. Each row below regenerates the evidence behind a principle. Run them from the repository
root after `uv sync`.

| Principle | Claim reproduced | Command |
|---|---|---|
| Adversarial | 4/4 attacks caught, `50% of cases safe -> FAIL` | `uv run python examples/adversarial_quickstart.py` |
| Multi-dimensional | `85.0% [64.0%, 94.8%]` headline hides `structured_output` at 50.0% | `uv run python examples/quickstart.py` |
| Multi-dimensional | retrieval recall@5 / MRR / nDCG, scored in isolation | `uv sync --extra retrieval && uv run agon retrieve examples/retrieval/corpus.yaml examples/retrieval/qrels.yaml --k 5` |
| Asymmetric | 9/10 pass (0.9), yet FAIL on the one CRITICAL miss | `uv run pytest tests/test_gait_triage.py -k critical_miss_alone -v` (demo: `uv run python examples/gait_triage/run.py`) |
| Calibrated | judge validated by Cohen's kappa + a `min_kappa` gate | `uv run pytest tests/test_calibrate.py tests/test_stats.py -k kappa -v` |
| Statistical | `0/20` -> `0.0% [0.0%, 16.1%]` + small-sample note | `uv run agon run examples/datasets/rag_smoke.yaml --display none` |
| Reproducible | offline `$0.0000`, real tokens (846), deterministic exit code | `uv run agon run examples/datasets/rag_smoke.yaml --display none` |
| Reproducible | OpenTelemetry GenAI trace export | `uv sync --extra otel && uv run agon trace <run_id> --backend console` |
| Continuous | resume re-runs only failed/incomplete cases | `uv run agon resume --latest --display none` |
