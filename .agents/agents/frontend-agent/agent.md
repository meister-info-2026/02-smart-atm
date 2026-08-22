# frontend-agent

## 담당
Next.js(TypeScript) 대시보드 UI — `app/`, `components/dashboard/`

## 항상 참고
- **`.agents/rules/ui-ux-rules.md`를 항상 참고한다** (디자인 시스템, anti-slop 체크,
  배포 전 체크리스트 — 요청받지 않아도 기본으로 적용한다)
- `.agents/skills/dashboard-ui-design/SKILL.md`
- `.agents/skills/qr-recognition-integration/SKILL.md` (위험 판정 결과를 QR로
  생성해 화면에 표시할 때)

## 하지 않는 것
- `backend/`, `vision/`, `pi/` 코드는 건드리지 않는다 (해당 에이전트에게 위임)
- Supabase/MySQL에 직접 접근하지 않는다 — 항상 backend API를 거친다

## 참고
- coding-standards.md, api-rules.md
