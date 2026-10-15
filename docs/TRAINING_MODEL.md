# Practice comparison model

The `practice-1` model compares support decks under a shared practice plan.
It estimates successful-practice gains and starting support bonuses. It is
not a whole-career simulator or a race-performance model.

## Data and levels

The user's MDB supplies `support_card_data`, `support_card_effect_table`,
`support_card_unique_effect`, `support_card_limit`, `single_mode_training_effect`,
`card_data`, `card_rarity_data` and `single_mode_scenario`.

Owned level comes from the exported level or EXP thresholds and is capped by
the exported limit breaks. Borrowed level and limit breaks are entered in the
practice plan. Unknown owned levels retain their unknown label and use level 1
effects conservatively. Missing effect rows are disclosed.

Effect curves interpolate linearly between nonnegative anchors and round down.
`-1` means an absent anchor. A newly unlocked effect stays zero before its first
known level. Unique effects apply only at their MDB unlock level. Ordinary and
unique friendship/specialty effects combine multiplicatively; flat bonuses,
training effects and mood effects add within their respective groups.

The scenario IDs are resolved against the supplied game's scenario catalogue:

| ID | Editor name |
| --- | --- |
| 1 | URA |
| 2 | Unity Cup |
| 3 | Our Grand Concert |
| 4 | Trackblazer |

Normal level 1 and summer/max-level practice values come from the MDB. Levels
2–4 use the observed facility-step schedule, normalized to those endpoints.
This includes URA Guts' larger fourth-level step and the different secondary-stat
steps. New scenarios are unsupported until their data and stepping are checked.

## One successful practice

For a stat channel with a positive base gain:

```text
(base + participating support flat bonuses)
× (1 + trainee growth / 100)
× (1 + mood × (1 + summed mood effects / 100))
× (1 + summed training effects / 100)
× product of active friendship multipliers
× (1 + 0.05 × participating characters)
```

Mood is `0.2`, `0.1`, `0`, `-0.1` or `-0.2`. A support's friendship multiplier
applies only to its matching practice at bond 80 or above. Its ordinary and
unique multipliers remain separate factors. Bonuses do not create a stat gain
where the practice has no base channel. Skill points have no trainee growth.
Each gain is capped at 100 and rounded down. The post-1200 conversion halves
the part beyond 1200. Energy-cost reduction and Wit friendship recovery are
calculated separately.

Supported conditional unique types are 101–105, 108–111 and 113–115, including
bond thresholds, off-specialty bonuses, support-type variety, fan counts,
maximum energy, total bond, participant count, facility level and active
friendship. Type 105 contributes starting stats; type 115 can add initial bond.
Unsupported conditional effects are excluded and labelled. Growth-by-friendship
count, outings, group friendship and failure effects are not assumed to be
active merely because a card is equipped.

## Deck expectation and ranking

For regular supports, specialty placement has weight
`(1 + normal specialty / 100) × (1 + unique specialty / 100)`. Each other
practice has weight 1 and absence has weight 0.5. Friend/group presence uses
equal weights for five practices and absence, without modelling outings or
group friendship. The estimate enumerates participant subsets. Placements are
assumed independent; if all six land together, one is dropped uniformly to
respect the five-character limit. This is a placement approximation, not a
complete turn-generation model.

The saved plan supplies practice counts, a fixed comparison facility level,
mood, energy and maximum energy. Early practices use initial bond and zero fans;
the later fraction uses bond 100 and the entered fan count. Default comparison
conditions are 50 practices, level 3 facilities, Great mood, 60% later practices,
70/100 energy and 100,000 later-stage fans. These are editable assumptions.
They are not inferred probabilities or a recommended training policy.

The displayed subtotal combines the owned rarity's starting stats, support
starting bonuses and expected practice gains. For crossing 1200, the aggregate
practice gain is converted approximately and limited by base/scenario caps.
Inheritance gains and their cap extensions are excluded. Race/event rewards,
teammates, concerts/lessons, shop effects, recovery, failed practices and the
choice of a practice after seeing the board are also excluded.

With stat targets, quality is the mean fraction of each positive target covered
by that subtotal, capped at one per target. With no targets, the five subtotals
have equal weight. Practice skill points break ties; they are not a skill tier
list or a race score. A support's single-card marginal contribution screens
decks with saturation at the targets, then retained decks are evaluated jointly
for their friendship and other interactions.

Search keeps up to 256 states per deck size, distinguishing skill coverage and
support-type composition, then up to three compositions per coverage mask.
The existing parent shortlist retains up to 80 pairs per trainee. This is
bounded search and can miss a better deck or lineage. Parents' blue starting
stats, affinity and future inheritance probabilities do not yet affect the
practice subtotal; use the original Lineage linker for those diagnostics.

## Checks and historical results

Imported career snapshots provide enabled in-game practice previews. The model
compares the five stats and skill points using their actual participants, levels,
bond, facility level, growth and mood. It deduplicates observations with identical
relevant inputs and skips previews with unmodelled teammates, character
conditions or unsupported support effects. A disagreement disables practice
sorting for that search and is reported in the setup summary. With no comparable
previews, the tested formula remains available but the panel states that no
personal preview check was possible.

These checks do not establish accuracy across complete careers, every scenario
or mature friendship stacks. Unit tests separately cover multiplicative
friendships, unlocks, borrowed caps, facility steps, conditions, placement,
energy effects, post-1200 conversion and lower-level cards beating weaker
higher-level cards. Private exports and their screenshots are not bundled.

Completed veterans are shown separately as reference outcomes for the same
trainee and scenario, ordered by support-card overlap. Levels, decisions and
rewards may differ. They are not fitted to the practice estimate, and no causal
claim or success probability is inferred from them. Saved plan estimates retain
their conditions and data fingerprint; a fresh search is required after imports.

## Formula references

The mathematical relationships were checked against the primary simulator
implementation at `mee1080/umasim` commit
`cf9366f6a487bd8f197b53d8a11981207beb9f6c`:

- [Practice formula and placement](https://github.com/mee1080/umasim/blob/cf9366f6a487bd8f197b53d8a11981207beb9f6c/core/src/commonMain/kotlin/io/github/mee1080/umasim/simulation2/Calculator.kt)
- [Support multipliers](https://github.com/mee1080/umasim/blob/cf9366f6a487bd8f197b53d8a11981207beb9f6c/core/src/commonMain/kotlin/io/github/mee1080/umasim/data/SupportCard.kt)
- [Conditional effect definitions](https://github.com/mee1080/umasim/blob/cf9366f6a487bd8f197b53d8a11981207beb9f6c/core/src/commonMain/kotlin/io/github/mee1080/umasim/data/SupportCardSpecialUnique.kt)
- [URA facility values](https://github.com/mee1080/umasim/blob/cf9366f6a487bd8f197b53d8a11981207beb9f6c/core/src/commonMain/kotlin/io/github/mee1080/umasim/scenario/ura/UraStore.kt)

The Python implementation is independently written. No simulator source code
or external game dataset is bundled; support effects and scenario endpoints
come from the user's local MDB. This is a community model, not an official
Cygames specification.
