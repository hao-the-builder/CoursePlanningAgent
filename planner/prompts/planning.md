# Plan $paths paths for this student

## Who they are

- Program: **$program** ($program_title), cohort $cohort, $years years
- Minor: $minor
- Data tier: **$tier** — $tier_note

$profile_summary

## The terms they have

$term_table

- Terms to keep free: $free_terms
- Terms on exchange: $exchange_terms
- Credits per term: between $workload_min and $workload_max
- Workload shape asked for: **$spread**

## The credit budget

The degree needs **$degree_credits credits**. The requirements below come to
about **$required_credits**, which leaves roughly **$free_credits credits of
free electives** that you still have to choose and place. A plan that only
covers the named requirements is 30-odd credits short and will fail.

Every path lists **every course in every term** — around $expected_rows rows.
Do not abbreviate, do not write "and so on", do not leave a term out.

## What the program requires

$requirements

## Already done

$already_done

## Your tools

$tool_summary

`draft_plan` is the one to start with. It returns a complete, feasible plan
built by code from the rules above — correct but unimaginative. Call it once
per path with a different `spread`, then change what you want to change and
explain the result. You are not obliged to keep what it gives you.

## What to send back

One JSON object, nothing before or after it:

```json
{
  "paths": [
    {
      "name": "Four words naming the idea, e.g. AI depth, even load",
      "summary": "Two or three sentences a student would actually read.",
      "why_it_fits": [
        "One reason per line, each quoting something the student asked for."
      ],
      "trade_offs": ["What this path costs them. At least one."],
      "plan": [
        {"code": "COMP 2011", "term": "Y1 Spring", "status": "planned"},
        {"code": "SLOT:CC-A", "term": "Y2 Fall", "status": "planned"}
      ],
      "slot_suggestions": {
        "SLOT:CC-A": ["two or three real course codes you looked up"]
      }
    }
  ]
}
```

Rules for the `plan` list:

- `status` is one of `taken`, `current`, `planned`, `transfer`, `exchange`.
- Carry over every row under "Already done" unchanged.
- An exchange row needs `host_course`, `host_university` and
  `mapping_approved: false`.
- A term label is exactly one of the labels in the term table, or `Transfer`.

## Make the paths genuinely different

$paths paths that differ only in the order of two electives are one path
written three times. Differ on something the student would actually weigh:
with an exchange term against without; a depth area against a breadth of
areas; finishing early against a lighter load throughout. Say in
`trade_offs` what each choice costs.
