# agent-driven-development_v2 — 仕様駆動開発（SDD）スキルセット

「〜を作って」と言うだけで、仕様→計画→実装→検証をユーザー承認ゲート付きで進める
汎用ワークフロー。superpowers（プロセス規律）と spec-kit（フェーズ構造）を参考に構築。

## 使い方

- **新規開発**: 「TODO アプリを作って」→ `sdd` が自動発火し、フェーズを順に進める
- **再開**: 「続きから」「開発を再開して」→ `specs/*/state.md` から現在フェーズに復帰
- **小規模修正**: 1〜2ファイルの修正は spec-lite によるバイパスルート（判定は sdd が行う）
- 各フェーズスキル（`sdd-specify` 等）は単体でも呼び出し可

## フェーズ

```
constitution → specify → clarify → plan → tasks → analyze → implement → verify
（原則策定）   （仕様）  （曖昧解消）（技術計画）（分解） （整合検証） （実装）  （受入検証）
```

各フェーズの完了にはユーザー承認が必須（clarify のみ曖昧箇所ゼロなら自動通過）。
実装はサブエージェント駆動＋TDD、小タスクは本体で直接。

## 成果物とテンプレート

| 成果物 | 生成フェーズ | テンプレート |
|---|---|---|
| `docs/constitution.md` | constitution（初回のみ） | `templates/constitution.md` |
| `specs/NNN-機能名/spec.md` | specify | `templates/spec.md` |
| `specs/NNN-機能名/clarifications.md` | clarify | （spec の Q&A 記録。書式は sdd-clarify 参照） |
| `specs/NNN-機能名/plan.md` | plan | `templates/plan.md` |
| `specs/NNN-機能名/tasks.md` | tasks | `templates/tasks.md` |
| `specs/NNN-機能名/spec-lite.md` | バイパス時のみ | `templates/spec-lite.md` |
| `specs/NNN-機能名/state.md` | sdd が管理 | 書式は `.claude/skills/sdd/SKILL.md` が正 |

## 構成

```
.claude/skills/   sdd（オーケストレーター）＋8フェーズスキル
templates/        成果物テンプレート5種
specs/            機能ごとの成果物（NNN- 連番）
docs/             constitution.md（初回に生成）
```
