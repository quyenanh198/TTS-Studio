# TTS Studio — Design System

> Nguồn sự thật cho giao diện: `frontend/src/index.css` (token) + `frontend/src/components/ui.tsx` (kit).
> File này giải thích **vì sao**; `MASTER.md` là khuyến nghị gốc từ ui-ux-pro-max; `design-tokens.json` là bản mirror máy đọc được; `design-preview.html` xem nhanh.

## 1. Định vị

- **Loại sản phẩm:** công cụ desktop chuyên nghiệp (audio creator: TTS · transcript · clone). Người dùng làm việc nhiều giờ, mắt cần nghỉ → **dark-first**, light mode đầy đủ.
- **Style:** Modern Dark (theo database: "Developer tools / pro productivity / AI tool interfaces"). Không glassmorphism nặng, không gradient trang trí, không animation scroll.
- **Dials:** Variance 4 (cân bằng), Motion 3 (tinh tế), Density 7 (khá dày — nhiều control, ít khoảng trắng thừa).

## 2. Màu

Kiến trúc **3 lớp**: primitive (`--navy-850`) → semantic (`--surface`) → component (`.card`). Component **không bao giờ** dùng hex trực tiếp.

| Vai trò | Dark | Light | Lý do |
|---|---|---|---|
| Nền / Surface | navy-900 / navy-850 | slate-50 / white | Navy có sắc tím-xanh nhẹ, không phải #000 (tránh OLED smear, mắt đỡ mỏi) |
| Chữ | #f1f3f9 / slate-400 / slate-450 | slate-900 / slate-550 / slate-500 | 3 mức: chính · phụ · mờ — tất cả ≥ 4.5:1 |
| **Primary / CTA** | orange-500 (chữ tối) | orange-700 (chữ trắng) | Cam ấm = "audio", nổi bật trên navy, chỉ dùng cho hành động chính (Tạo giọng nói, Bắt đầu, Tải) |
| Secondary | indigo (soft) | indigo-600 | Trạng thái chọn/active, focus ring, nav hiện tại — không tranh chấp với CTA |
| Success / Warning / Danger / Info | green / amber / red / cyan | phiên bản tối hơn | Trạng thái job & alert; luôn kèm icon + chữ, không chỉ dựa màu |

Đã bỏ tím `#7c5cff` (AI-slop) và gradient logo. Contrast đo thực tế trên phần tử render (kể cả chữ trên nền `*-soft`, hover, chip active) — mọi cặp ≥ 4.5:1 ở cả hai theme; xem `design-tokens.json → contrast` và bảng live trong `design-preview.html`.

## 3. Chữ

- **Inter Variable** (self-hosted qua `@fontsource-variable/inter` — app offline không phụ thuộc Google Fonts), fallback Segoe UI.
- Base **14px** cho desktop dense; body line-height 1.5; số dùng `tabular-nums`.
- Thang: H1 22/bold, card title 15/bold, body 13–14, meta 11–12, tag/kbd 10.5–11 uppercase. Không nhỏ hơn 10.5px.

## 4. Không gian, bo góc, độ sâu

- Spacing 4/8/12/16/20/24/32; card padding 20; gap giữa card 16.
- Radius: sm 6 (tag, focus) · md 10 (nút, input) · lg 14 (card) · pill (chip).
- Bóng rất nhẹ (`shadow-sm`); glow cam chỉ trên hover nút primary và logo. Không blur.

## 5. Component kit (`components/ui.tsx` + class trong `index.css`)

| Thành phần | Class / Component | Trạng thái bắt buộc |
|---|---|---|
| Nút | `.btn-primary` `.btn-secondary` `.btn-ghost` `.btn-outline` `.btn-danger` (+`.btn-sm` `.btn-lg`), `.btn-icon` | hover, active (`scale .98`), disabled (opacity .45, `cursor: not-allowed`), loading (spinner), focus-visible ring |
| Field | `.input`, `<Field label help>` (`useId` → `htmlFor`/`aria-describedby`) | hover border, focus ring 2px, disabled, placeholder subtle |
| Segmented | `<Segmented>` (`radiogroup`/`radio`, roving tabindex, phím mũi tên) | thay thế nhóm nút tab tự chế |
| Chip lọc | `.chip` / `.chip-active` (`aria-pressed`) | dùng cho bộ lọc & định dạng |
| Card | `<Card title icon right>` | tiêu đề 15px + icon 24px nền indigo-soft |
| Progress | `<ProgressBar>` (`role=progressbar`) | màu theo trạng thái |
| Status | `<StatusTag>` `.tag-*` | queued/running/done/error/cancelled |
| Alert | `<Alert kind>` | icon + text; danger là `role=alert` |
| Empty state | `<EmptyState icon title hint action>` | mọi danh sách rỗng đều có |
| Skeleton | `<Skeleton>` | khi tải danh sách giọng, hệ thống |
| Toast | `<ToastHost>` + `toastOk/toastError` | phản hồi mọi hành động async; tự tắt 4 s (lỗi 8 s) |
| Voice | `<VoiceAvatar>` `<LangBadge>` | chữ cái đầu + màu theo giới tính/clone; mã ngôn ngữ thay cờ emoji |

## 6. Tương tác & chuyển động

- Thời lượng 120/180/260 ms, easing `cubic-bezier(.16,1,.3,1)`. Chỉ animate `background/color/box-shadow/transform/opacity`.
- `prefers-reduced-motion` → tắt toàn bộ transition/animation.
- Phím tắt: `Ctrl+1..5` đổi trang, `Ctrl+Enter` tạo giọng nói (hiển thị `<kbd>` trên nút).
- Kéo-thả file: viền đổi màu primary khi hover file.

## 7. Truy cập (a11y)

- Focus ring 2px indigo cho mọi phần tử tương tác (`:focus-visible`), không bao giờ `outline: none` trần.
- Nút chỉ-icon luôn có `aria-label`; danh sách giọng là `listbox/option` với roving tabindex (↑↓ Home End PgUp PgDn, Enter chọn, P nghe thử) + `aria-activedescendant`; nav dùng `aria-current`; toast là live region luôn mount (`status`/`alert`).
- Trang giữ nguyên trạng thái khi chuyển tab (mount ẩn) — không mất sách đã phân tích, cue đang sửa, bản ghi âm.
- Mục tiêu bấm ≥ 36 px (desktop), sidebar item 44 px.
- Không dùng emoji làm icon; màu trạng thái luôn kèm chữ/icon.

## 8. Anti-pattern đã loại

Gradient tím-xanh mặc định · emoji làm icon · nút không hover/disabled · lỗi chỉ hiện inline một chỗ · text < 12px xám trên xám · animation trang trí.

## 9. Cách mở rộng

1. Cần màu mới → thêm **primitive** rồi map sang **semantic** cho cả dark & light; đo contrast (script trong `design-preview.html`).
2. Cần component mới → thêm class vào `@layer components` hoặc component vào `ui.tsx`; tái dùng token; viết đủ 5 trạng thái.
3. Trang mới → dùng `PageHeader` + `Card` + max-width 1440, grid 2 cột ≥ 1280px.
