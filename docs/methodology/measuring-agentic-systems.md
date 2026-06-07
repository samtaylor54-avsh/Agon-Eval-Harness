# What We Measure When We Measure an Agentic System

*Trust is earned through opposition — notes on evaluation as an adversarial discipline.*

*A demo proves a system can succeed once, under conditions you chose. An evaluation proves it survives being opposed — measured from hostile angles, across edge cases, and again after every change. This essay argues that measuring an agentic system is an inherently adversarial discipline, and shows what that discipline looks like when it is actually built.*

## The Challenge: a demo is not an evaluation

The AI industry is excellent at demonstrations and weak at evaluation. A demo answers one question — can this system do the thing? — and answers it under the most favorable conditions available: curated inputs, a forgiving judge, an audience that wants to believe. It is a performance, and there is nothing wrong with performances. But a performance is not a test of reliability, and reliability is the only thing that matters when the system is running without you watching.

An evaluation answers harder questions. Does it reliably work — not once, but across the distribution of real inputs it will encounter? Under what conditions does it fail, and how badly? Is it improving or quietly regressing as the model underneath it changes? These questions cannot be answered by watching a system succeed. They can only be answered by watching it fail — deliberately, repeatedly, and under conditions designed to find the failures that matter most.

The Greeks had a word for the kind of contest that produces excellence through opposition: *agon*. The term names a structured competition — athletic, rhetorical, dramatic — undertaken not to destroy an opponent but to draw out the best in both parties. Purposeful opposition in service of improvement. The contestant who faces no real contest learns nothing; the system that faces no real evaluation proves nothing. The *agon* is the mechanism by which excellence is separated from the appearance of excellence.

That is the thesis of this essay: to measure an agentic system is to oppose it. Not casually, not optimistically, not with a set of toy examples the system's designers already know it can handle — but systematically, with tests designed to find failures, at the edges of stated capability, and with the honesty to report what breaks. What you measure is the structured record of how hard you tried to break the system and what withstood the attempt. Trust is not demonstrated by success; it is earned by surviving challenge.

What follows is that argument in seven principles, each corresponding to a stage of the contest. The principles are not abstract — each is grounded in a working harness called Agon-Eval-Harness, where the claim is not that these ideas are good but that they are implemented, tested, and observable. The seven stages cover the adversarial nature of evaluation itself, the multi-dimensional character of what must be measured, the asymmetry that makes some failures far worse than others, the calibration required before any judge can be trusted, the statistical discipline that separates signal from noise, the reproducibility that makes results meaningful across time and teams, and the continuous feedback loop that converts every discovered failure into a permanent fixture of the test suite.

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

Consider what the harness actually reports on a standard offline run. The headline reads: **85.0% [64.0%, 94.8%] (17/20), Recommendation: INVESTIGATE**. That number is technically accurate. A reasonable person glancing at a dashboard could read it as reassuring — 85% passing, confidence interval above 64%, only three failures. But break it down by category and the picture changes immediately. The `classification`, `smoke`, and `summarization` categories all pass at **100.0%**, and those results are doing most of the arithmetic. Meanwhile, `structured_output` passes at **50.0%** and `robustness` at **66.7%**. The aggregate does not report 50%; it buries 50% beneath the categories that happened to perform well.

The per-risk breakdown compounds this. High-risk cases pass at **66.7%**. These are not equivalent to low-risk misses — they are the cases where failure costs the most. The aggregate treats a high-risk failure and a low-risk success as interchangeable items in a ratio. They are not. The headline's 85.0% is anchored by the easy cases; the hard and consequential ones are the ones it is hiding.

The harness is built around a framework of **seven evaluation categories tracked distinctly**: Functional Correctness, Tool Use, Planning, State Management, Robustness, Reliability, and Safety. These are not the column headers in any single report — they are the conceptual architecture that determines what must be measured independently and what cannot be averaged away. The per-category and per-risk breakdowns are the practical expression of that principle: refuse the single number, and `structured_output` at 50.0% becomes visible when the headline would have buried it.

The same logic applies with even more force to the separation between retrieval and generation in a RAG system. A pipeline that produces poor answers has two distinct failure modes: the retriever returned wrong content, or the model generated a bad answer despite correct content. These call for different diagnoses and different fixes. If retrieval recall and answer quality share a score, you cannot tell which failure you have.

The retrieval evaluation runs on its own axes: `hr_policy_qrels [bm25]: recall@5=1.000 MRR=0.969 nDCG@5=0.967 hit@5=1.000`. These are not components of some larger answer-quality score; they are self-contained evidence about the retriever's behavior, measured at the boundary where retrieval hands off to generation. When the harness flags a RAG failure — a case like `rag_020`, failed for `missing_citation` — you can ask whether retrieval was complete before asking whether generation was accurate. Isolation is what makes the failure legible.

Collapse is a form of concealment, and measurement is only useful if it preserves the distinctions you might need to act on. The contestant in the arena does not improve by being told they scored well overall. They improve by learning which event broke down, at what moment, and why. Multi-dimensional measurement is not completeness for its own sake; it is the minimum resolution at which the data becomes actionable.

## The Rules II: measurement is asymmetric

## The Judges: measurement must be calibrated

## The Record I: measurement is statistical

## The Record II: measurement is reproducible

## The Transformation: measurement is continuous

## Through Agon

## Reproduce Every Claim
