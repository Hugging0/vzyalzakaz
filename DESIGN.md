# Design System

## Overview

Hunt Agent — Telegram-first рабочий инструмент с метафорой signal: он отсекает шум и выделяет сильные возможности. Визуальный язык спокойный, собранный и профессиональный.

## Colors

Light: background `#F6F7F9`, surface `#FFFFFF`, primary ink `#121417`, secondary ink `#344054`, muted `#667085`, border `#EAECF0`, deep green `#123A2B`, signal green `#35C983`, soft green `#ECFDF3`, info `#2E6BE6`, warning `#D97706`, danger `#D92D20`.

Dark: background `#0E1114`, surface `#15191E`, elevated `#1B2026`, primary text `#F5F7FA`, secondary text `#C5CBD3`, muted `#8B949E`, border `#2A3038`.

## Typography

Inter with a system sans-serif fallback. Use dense but readable product typography: screen headings 24px, section headings 18px, card titles 16px, body 15px, metadata 12px or larger.

## Components

Build and reuse `AppButton`, `AppCard`, `AppBadge`, `AppNotice`, `AppField`, `AppSwitch`, `AppSheet`, `AppEmptyState`, and `AppSkeleton`. Domain components should compose these primitives rather than create alternate visual systems.

## Layout & Motion

Mobile-first single column with Telegram safe-area-aware fixed navigation. On wide web use a constrained content column or master-detail layout. Use 12/16/20/24px radii and subtle borders instead of heavy shadows. Motion is 140–220ms, state-driven, and disabled for reduced motion.
