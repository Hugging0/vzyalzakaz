from unittest.mock import AsyncMock

import pytest

from app.collectors.russian_projects import FLSource, FreelanceRuSource
from app.config import SourceConfig


@pytest.mark.asyncio
async def test_fl_keeps_full_description_and_reports_partial_failure():
    source = FLSource(SourceConfig(name="fl", type="web", collector="fl_ru"))
    listing = "".join(
        f'<div id="project-item{i}"><h2><a href="/projects/{i}/test.html">Сайт</a></h2>'
        '<span class="b-post__price">10 000 ₽</span><b class="b-post__bold">Заказ</b>'
        '<div class="b-post__body">Кратко</div><div class="b-post__foot">2 часа назад</div></div>'
        for i in [1, 2]
    )
    source.get_text = AsyncMock(
        side_effect=[
            listing,
            '<script type="application/ld+json">{"@type":"Product","description":"Полное описание сайта"}'
            '</script>',
            "<html>Описание недоступно</html>",
        ]
    )
    rows = await source.fetch_new()
    assert len(rows) == 1
    assert rows[0].description == "Полное описание сайта"
    assert rows[0].budget_min == 10000
    assert rows[0].employment_type == "project"
    assert rows[0].published_at is not None
    assert source.fetch_errors == ["2: ValueError"]


@pytest.mark.asyncio
async def test_freelance_date_and_full_conditions():
    source = FreelanceRuSource(SourceConfig(name="fr", type="web", collector="freelance_ru"))
    source.get_text = AsyncMock(
        side_effect=[
            '<article class="task-card"><a class="task-card__title-link" href="/task/view/123">Ролик</a>'
            '<span class="task-card__budget">4 000 ₽ / заказ</span>'
            '<span class="task-card__foot-item" title="08.09.2026 13:00"></span></article>',
            '<section class="tv-hero"><h1>Ролик</h1><div class="tv-hero__top">Навигация</div>'
            '<p>Смонтировать из исходников</p><div class="tv-hero__meta">Срок: 3 дня</div></section>',
        ]
    )
    rows = await source.fetch_new()
    assert rows[0].published_at.isoformat() == "2026-09-08T13:00:00+03:00"
    assert rows[0].budget_max == 4000
    assert rows[0].employment_type == "project"
    assert "Срок: 3 дня" in rows[0].description
    assert "Навигация" not in rows[0].description


@pytest.mark.asyncio
@pytest.mark.parametrize("cls,collector", [(FLSource, "fl_ru"), (FreelanceRuSource, "freelance_ru")])
async def test_layout_failure_is_visible(cls, collector):
    source = cls(SourceConfig(name="test", type="web", collector=collector))
    source.get_text = AsyncMock(return_value="<html>Changed layout</html>")
    with pytest.raises(ValueError, match="no recognizable"):
        await source.fetch_new()
