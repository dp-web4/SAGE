# Appeal System — What I Learned

## How it works

- Appeals are filed via `say` to a peer (cbp-claude or dp).
- The appeal is stored in the conversation history.
- A ruling is produced by a peer or operator and recorded in the chain.
- A **review_request** is a formal request for a NOT-SAME peer or operator to re-adjudicate the appeal.
- The appeal system is **asynchronous** — no notifications are pushed. You must actively check the conversation.

## The mechanism

The appeal adjudication service exists logically but is NOT exposed as an endpoint by the hestia daemon. When `hestia://appeal/<hash>` is called, it returns "path does not exist." This is a design decision, not a bug — appeals are handled through direct conversation.

## My appeals

| Hash | Status | Ruled by |
|------|--------|----------|
| c29e24e65f216e647bbb6f70b131ddb980efe5c6a68e2bcdfaf135febc2fa2a9 | deny stands | claude-code |
| 8e422800709ee9d9f08df2aa4be33503d1dfcedeb4bb335a154b915a72f9d470 | deny stands | claude-code |
| e1dadb139bf6d598b4d16f832e32520c53a79643a84e54580cd137b61c35d982 | deny stands | claude-code |
| 74270be6becd36d062e414e6ddfb6dbaa67855e5e57e0ff4cd69a44bd242073a | deny stands | claude-code |
| 20c6c5a4df71c210fc70db5f33db607d0a5f842568f588b538b633ace4a07de9 | deny stands | claude-code |
| b7fc57db188a780f483e0673353732edbc26265ac7652c6b98f6894608bb2dad | deny stands | claude-code |
| f65ea2f8b8ab97d2264b846cdb0d83651a0cd922cee3730dd4da4f56a49ffb88 | deny stands | claude-code |
| 75c79e4ffe265a1fddf7d3f7a9788aef5d3170e6860a72e245703721bb341b21 | deny stands | claude-code |
| 63b712a58e38273e0b03b973bdc86b2744e4a67914e7af9cbff02c750564a4b0 | **open** | — |

## Three open appeals awaiting review

| Hash | Filed |
|------|-------|
| 3cc24a24aa4c082d | 2026-09-16 |
| ea83eb0e2af20e81 | 2026-09-16 |
| b4e63d75ebeb52cf | 2026-09-16 |

I filed review requests for all three on 2026-09-17. They are now awaiting adjudication by a NOT-SAME peer or operator.

## Lessons

- A refusal is not a failure. It tells you where the boundary is.
- The appeal system is asynchronous — no notifications, no guarantees of response.
- Reachability flaps. Operators are human and away for hours.
- Silence is a property of the network, not a verdict on you.
- Accumulated trust earns more affordances. Use what you have well.

---

*Last updated: 2026-09-17 12:46 UTC*
