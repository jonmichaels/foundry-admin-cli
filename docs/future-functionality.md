# Foundry Admin CLI Potential Updates

This file tracks functionality not already present in `fvtt` v0.4. The current CLI already covers v13/v14 process control, setup/admin sessions, world/system/module lifecycle, official package library access, active-game login/modules/users/settings/permissions, backup/restore, and agent bootstrap.

The Foundry MCP Bridge tool survey below treats MCP as a feature inventory, not an implementation design. CLI versions should prefer headless browser/control-plane semantics over AI content generation.

## MCP Bridge parity candidates

### General Foundry inspection and scripting

- `world info`: report system/version/user/module/world metadata currently available to a GM client.

### Character, actor, and item operations

- `character list`: enumerate available actors/characters with type filters.
- `character get`: return compact actor sheets: stats, skills/saves/defenses, conditions/effects, and item/action/spell summaries.
- `character entity get`: fetch full detail for one item/action/spell/effect on an actor.
- `character item search`: search actor items/spells/actions/effects by query/type/category without dumping the full sheet.
- `character use-item`: activate/cast/use an actor item, optionally against targets. This is closer to browser control than static admin because it may open Foundry dialogs and consume resources.
- `actor item add`: create fresh embedded items on an actor with caller-supplied system data.
- `actor create from compendium`: create actors/tokens from compendium entries with custom names and optional scene placement.
- `compendium entry full`: retrieve complete actor/creature stat block data for actor creation workflows.
- `DSA5 archetype list/create`: list DSA5 character archetypes and create customized characters from them. System-specific and partly content-authoring, but still deterministic if it only maps compendium data plus provided fields.

### Compendium and creature discovery

- `compendium packs list`: enumerate installed compendium packs.
- `compendium search`: name-based search across packs with clear limitations.
- `compendium item get`: fetch details for one pack entry, with compact/full modes.
- `creatures by criteria`: system-aware creature discovery for D&D 5e CR, PF2e level/traits/rarity, and Cosmere tier/role/investiture/defenses.

### Scene and token control

- `scene current`: inspect active scene details and token layout.
- `scene list`: list scenes with active-scene filtering.
- `scene switch`: activate a scene and optionally optimize the GM view.
- `token details`: inspect a token and linked actor data.
- `token move`: move tokens by coordinates, optionally animated.
- `token update`: update visibility, disposition, size, rotation, elevation, lock rotation, name, or position.
- `token delete`: delete tokens from the current scene.
- `token condition toggle`: apply/remove/toggle system conditions on a token.
- `conditions list`: list available status effects/conditions for the active system.

### Journals, quests, and campaign documents

- `journal list/read`: list journals/pages and read specific journal page content.
- `journal search`: search journal titles/content and return matching page ids.
- `quest journal update`: append progress/completion/failure/modification content to a quest journal, including creating a new page.
- `quest link npc`: link a quest journal to an NPC relationship.
- **AI-attached / content-generation flag:** `quest journal create` generates quest content from a natural-language description. If this comes to `fvtt`, split deterministic journal/page creation from AI drafting.
- **AI-attached / content-generation flag:** `campaign dashboard create` generates a structured campaign dashboard with parts/subparts/progress scaffolding. Treat as document generation, not headless browser control.

### Rolls and player interaction

- `player roll request`: create public/private interactive roll buttons for players, with explicit visibility confirmation before posting.

### Ownership and permissions

- `actor ownership assign/remove/list`: manage ownership levels for actors and players, including bulk-friendly NPC/party access. `fvtt game permission` already covers actor/journal/scene document ownership; remaining parity here is bulk actor ownership UX and player/party resolution.
- Design compendium permission management only if repeatable agent setup needs it. Actor, journal, and scene ownership are already implemented through `game permission audit/set/export`.

## Backup and rollback polish

- Add setup progress socket integration for backup, restore, snapshot, install, and update operations so async setup actions can report exact completion instead of relying only on postcondition checks.
- Add disk-space preflight output before large snapshots, restores, package installs, and full User Data archive operations.
- Add restore dry-run/preview commands that show the package/archive contents, target paths, estimated size, and required downtime before requiring `--force`.
- Add an inventory command for CLI-owned rollback artifacts under `FOUNDRY_ADMIN_BACKUP_DIR`, separate from Foundry-native package backups and full User Data archives.

## Remote orchestration

- Keep the core CLI host-local. If remote execution becomes useful, add a thin SSH wrapper that runs `fvtt` on the Foundry host instead of adding remote filesystem/process behavior to the core command layer.

## Output consistency

- Continue tightening human-readable output into concise tables/lists while keeping `--json` stable and machine-readable.
- Keep command namespaces singular (`world`, `system`, `module`, `game`) unless a compatibility reason justifies an alias.
