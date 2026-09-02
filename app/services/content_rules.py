from __future__ import annotations

import re
from dataclasses import dataclass

from app.models import ContentCategory

EN_ROLE = (
    r"(?:(?:python|react|frontend|front end|backend|back end|full[ -]?stack|software|"
    r"mobile|ios|android|ai|ml|data|devops|cloud|smm|seo|video|motion|graphic|"
    r"product|web|ui ?ux|ux ?ui|wordpress|shopify|telegram|content|marketing)\s+)?"
    r"(?:developers?|devs?|engineers?|designers?|editors?|marketers?|specialists?|"
    r"freelancers?|contractors?|copywriters?|writers?|managers?|analysts?|animators?|"
    r"illustrators?|recruiters?)"
)
RU_ROLE = (
    r"(?:(?:python|react|frontend|backend|фронтенд|бэкенд|бекенд|full[ -]?stack|ai|ml|"
    r"devops|smm|смм|seo|сео|видео|моушн|графическ\w*|продуктов\w*|web|веб|ui ?ux|"
    r"wordpress|telegram|телеграм|контент|маркетинг)[\s-]+)?"
    r"(?:разработчик\w*|программист\w*|инженер\w*|дизайнер\w*|монтаж[её]р\w*|"
    r"редактор\w*|маркетолог\w*|специалист\w*|фрилансер\w*|копирайтер\w*|"
    r"автор\w*|аналитик\w*|аниматор\w*|иллюстратор\w*|таргетолог\w*)"
)
ROLE = rf"(?:{EN_ROLE}|{RU_ROLE}|smm|смм|devops)"
EN_ROLE_PREFIX = r"(?:(?:an?|experienced|freelance|good|senior|junior)\s+){0,3}"


@dataclass(frozen=True, slots=True)
class IntentRule:
    category: ContentCategory
    code: str
    weight: float
    pattern: re.Pattern[str]


def rule(category: ContentCategory, code: str, weight: float, pattern: str) -> IntentRule:
    return IntentRule(category, code, weight, re.compile(pattern, re.IGNORECASE))


RULES: tuple[IntentRule, ...] = (
    # Demand-side: the object of search is a worker, or the author owns a task.
    rule(
        ContentCategory.JOB,
        "employer_intent:organization_hiring",
        8,
        rf"\b(?:we(?: are| re)?|our (?:company|agency|team)|my company|the company|"
        rf"our startup|the team)\s+(?:is |are )?(?:now |actively )?"
        rf"(?:hiring|looking for|seeking)\s+{EN_ROLE_PREFIX}{ROLE}\b",
    ),
    rule(
        ContentCategory.JOB,
        "employer_intent:hiring",
        7,
        r"\b(?:we are hiring|we re hiring|we're hiring|now hiring|looking to hire|"
        r"hiring for|opening for|position available|applications are open|join our team|"
        r"join our company|contract opportunity|freelance opportunity|job opportunity)\b",
    ),
    rule(
        ContentCategory.JOB,
        "employer_intent:looking_for_role",
        8,
        rf"\b(?:looking for|seeking)\s+{EN_ROLE_PREFIX}{ROLE}\b",
    ),
    rule(
        ContentCategory.JOB,
        "employer_intent:hiring_role",
        8,
        rf"\b(?:hiring|recruiting)\s+{EN_ROLE_PREFIX}{ROLE}\b",
    ),
    rule(
        ContentCategory.JOB,
        "employer_intent:role_needed",
        8,
        rf"\b{ROLE}\s+(?:is )?(?:needed|required|wanted)\b",
    ),
    rule(
        ContentCategory.JOB,
        "employer_intent:need_role",
        8,
        rf"\b(?:we need|need)\s+{EN_ROLE_PREFIX}{ROLE}\b",
    ),
    rule(
        ContentCategory.GIG,
        "employer_intent:urgent_paid_task",
        8,
        rf"\b(?:(?:need|seeking)\s+(?:an? )?{ROLE}\s+(?:asap|urgently)|"
        rf"{ROLE}\s+needed\s+(?:asap|urgently)|paid (?:task|gig)|urgent paid task)\b",
    ),
    rule(
        ContentCategory.PROJECT,
        "client_intent:someone_to_deliver",
        8,
        r"\b(?:looking for someone to|need someone who can|looking for someone who knows|"
        r"can someone (?:build|create|design|edit|fix|integrate|automate)|"
        r"who can help (?:with|us)|need help with|need this built|help us build)\b",
    ),
    rule(
        ContentCategory.JOB,
        "employer_intent:informal_referral",
        7,
        rf"\b(?:anyone know (?:an? |a good )?{ROLE}|freelancer needed|seeking contractor)\b",
    ),
    rule(
        ContentCategory.JOB,
        "employer_intent:ru_organization_hiring",
        8,
        rf"\b(?:(?:мы|компания|команда|агентство|студия)\s+)?"
        rf"(?:ищем|ищет|нанимаем|нанимает|приглашаем|приглашает)\s+"
        rf"(?:опытн\w+ |хорош\w+ )?{ROLE}\b",
    ),
    rule(
        ContentCategory.JOB,
        "employer_intent:ru_role_needed",
        8,
        rf"\b(?:ищу|нужен|нужна|нужны|требуется|требуются)\s+"
        rf"(?:опытн\w+ |хорош\w+ |срочно )?{ROLE}\b",
    ),
    rule(
        ContentCategory.GIG,
        "employer_intent:ru_urgent_task",
        8,
        rf"\b(?:срочно\s+(?:нужен|нужна|нужны)\s+{ROLE}|"
        rf"{ROLE}\s+(?:нужен|нужна)\s+срочно|оплачиваемая задача|разовая задача)\b",
    ),
    rule(
        ContentCategory.PROJECT,
        "client_intent:ru_task_owner",
        8,
        r"\b(?:кто (?:может|сможет) (?:сделать|разработать|настроить|смонтировать|"
        r"нарисовать|автоматизировать)|нужно (?:сделать|разработать|настроить|создать|"
        r"смонтировать|нарисовать|автоматизировать)|нужна помощь (?:с|в))\b",
    ),
    # Demand structure. These are corroborating evidence, not single-word verdicts.
    rule(
        ContentCategory.JOB,
        "job_structure:responsibilities",
        2.5,
        r"\b(?:responsibilities|you will be responsible for|candidate should|ideal candidate|"
        r"обязанности|кандидат должен|вам предстоит)\b",
    ),
    rule(
        ContentCategory.JOB,
        "job_structure:requirements",
        2.5,
        r"\b(?:job requirements|requirements include|required qualifications|"
        r"требования к кандидату|требования|необходимые навыки)\b",
    ),
    rule(
        ContentCategory.JOB,
        "job_structure:application",
        3.5,
        r"\b(?:apply here|dm to apply|send (?:us )?your (?:cv|resume|portfolio)|"
        r"applications are open|отправ(?:ьте|ляйте) (?:нам )?(?:резюме|портфолио)|"
        r"присылайте (?:резюме|портфолио)|для отклика)\b",
    ),
    rule(
        ContentCategory.PROJECT,
        "project_structure:scope",
        2.5,
        r"\b(?:project scope|scope of work|deliverables|milestones|technical brief|"
        r"техническое задание|техзадание|тз на|этапы проекта|результат работы)\b",
    ),
    rule(
        ContentCategory.PROJECT,
        "project_structure:payment",
        2.5,
        r"\b(?:paid project|fixed[ -]price|project budget|budget is|hourly rate|"
        r"оплачиваемый проект|фиксированная цена|бюджет\s+\d|оплата\s+\d|ставка\s+\d)\b",
    ),
    rule(
        ContentCategory.JOB,
        "job_structure:employment",
        2.5,
        r"\b(?:part[ -]time role|remote role|short[ -]term contract|long[ -]term contract|"
        r"\d+[ -]month contract|compensation|salary|зарплата|частичная занятость|"
        r"удаленная вакансия|удалённая вакансия)\b",
    ),
    # Candidate and resume direction.
    rule(
        ContentCategory.JOB_SEEKER,
        "candidate_intent:role_looking_for_work",
        9,
        rf"\b{ROLE}\b.{{0,80}}\b(?:looking for|seeking)\s+"
        r"(?:an? |new |freelance |contract )?(?:(?:\w+[ -]?){0,2})"
        r"(?:work|job|role|position|opportunit\w*|projects?|clients?|contracts?)\b",
    ),
    rule(
        ContentCategory.JOB_SEEKER,
        "candidate_intent:first_person_available",
        8,
        rf"\b(?:i am|i m|i'm)\s+(?:an? |freelance )?{ROLE}\b.{{0,120}}\b"
        r"(?:open to|looking for|seeking|available for|available immediately)\b",
    ),
    rule(
        ContentCategory.JOB_SEEKER,
        "candidate_intent:open_to_work",
        8,
        r"\b(?:open (?:to|for) (?:(?:\w+[ -]?){0,2})(?:work|projects)|"
        r"open to (?:new )?opportunities|"
        r"available for (?:(?:\w+[ -]?){0,2})(?:work|freelance|projects|contracts?|gigs)|"
        r"available immediately|i am (?:also )?available (?:for|if|to)|"
        r"actively looking|currently seeking)\b",
    ),
    rule(
        ContentCategory.JOB_SEEKER,
        "candidate_intent:looking_for_work",
        8,
        r"\b(?:looking for|seeking|in search of)\s+(?:an? |new |freelance )?"
        r"(?:(?:\w+[ -]?){0,2})(?:job|work|role|position|opportunities|projects|contracts?)\b",
    ),
    rule(
        ContentCategory.JOB_SEEKER,
        "candidate_intent:ru_first_person_search",
        9,
        rf"\bя\b.{{0,100}}\b{ROLE}\b.{{0,120}}\bищу\s+"
        r"(?:работу|проекты?|заказы?|клиентов?|подработку|контракт)\b",
    ),
    rule(
        ContentCategory.JOB_SEEKER,
        "candidate_intent:ru_search",
        8,
        r"\b(?:ищу|в поиске)\s+(?:(?:удален|удалён)\w+ |новую |фриланс |freelance )?"
        r"(?:работ[уы]|проекты?|заказы?|подработку|вакансию|контракт|projects?|work|job)\b",
    ),
    rule(
        ContentCategory.JOB_SEEKER,
        "candidate_intent:ru_available",
        7,
        r"\b(?:открыт|открыта|готов|готова|свободен|свободна)\s+"
        r"(?:к работе|к предложениям|к новым проектам|для проектов)\b",
    ),
    rule(
        ContentCategory.RESUME,
        "resume_structure:first_person_experience",
        6,
        r"\b(?:i have|i ve got|у меня)\s+\d+\+?\s+(?:years?|лет)\b.{0,30}"
        r"(?:experience|опыта)?\b",
    ),
    rule(
        ContentCategory.RESUME,
        "resume_structure:owned_profile",
        5,
        r"\b(?:my (?:experience|stack|tech stack|skills|portfolio|resume|cv)|"
        r"about me|i specialize in|мой опыт|мои навыки|мой стек|мое портфолио|"
        r"моё портфолио|мое резюме|моё резюме|обо мне|специализируюсь на)\b",
    ),
    rule(
        ContentCategory.RESUME,
        "resume_structure:experience",
        2.5,
        r"\b(?:\d+\+?\s+(?:years? of experience|years? experience|yoe|лет опыта)|"
        r"experience:\s*\d+|опыт работы\s+\d+)\b",
    ),
    # Service supply, including agencies. Employer phrases do not use these objects.
    rule(
        ContentCategory.AGENCY_OFFER,
        "provider_intent:agency_seeking_clients",
        10,
        r"\b(?:we are|we re|we're)\s+(?:an? )?(?:team|agency|studio)\b.{0,120}\b"
        r"(?:looking for|seeking|accepting)\s+(?:new )?clients\b",
    ),
    rule(
        ContentCategory.AGENCY_OFFER,
        "provider_intent:agency_services",
        8,
        r"\b(?:our agency|our studio|our team)\b.{0,80}\b"
        r"(?:provides|offers|can build|can develop|can help your business)\b|"
        r"\b(?:наше агентство|наша студия|наша команда)\b.{0,80}\b"
        r"(?:предлагает|оказывает|разрабатывает|поможет вашему бизнесу)\b",
    ),
    rule(
        ContentCategory.SERVICE_OFFER,
        "provider_intent:services",
        8,
        r"\b(?:we provide|we offer|i provide|i offer|our services|my services|"
        r"software development services|marketing services|design services|"
        r"предлагаю услуги|предлагаем услуги|оказываю услуги|оказываем услуги)\b",
    ),
    rule(
        ContentCategory.SERVICE_OFFER,
        "provider_intent:client_acquisition",
        9,
        r"\b(?:looking for clients|seeking clients|taking on new clients|accepting new clients|"
        r"booking new projects|dm me for work|hire me|available for commissions|"
        r"ищу клиентов|беру новые заказы|открыт для заказов|открыта для заказов)\b",
    ),
    rule(
        ContentCategory.SERVICE_OFFER,
        "provider_intent:sales_cta",
        7,
        r"\b(?:contact us for|book a consultation|get a quote|dm for pricing|packages from|"
        r"starting at [$€£]|закажите у нас|записаться на консультацию|цены от|"
        r"стоимость от|пишите за ценой)\b",
    ),
    rule(
        ContentCategory.SERVICE_OFFER,
        "provider_intent:cheap_services",
        8,
        r"\b(?:делаю|создаю|разрабатываю)\s+(?:сайты|ботов|дизайн|логотипы|рилсы|reels)"
        r"\b.{0,50}\b(?:недорого|на заказ|под ключ|от \d)\b",
    ),
    rule(
        ContentCategory.SELF_PROMOTION,
        "promotion:personal_work",
        7,
        r"\b(?:check out my (?:portfolio|work|case study|channel)|my latest (?:project|case)|"
        r"follow my channel|subscribe to my|посмотрите мое портфолио|посмотрите мой кейс|"
        r"мой новый кейс|подписывайтесь на мой канал)\b",
    ),
    # Other non-opportunity content.
    rule(
        ContentCategory.SPAM_OR_SCAM,
        "safety:income_scam",
        10,
        r"\b(?:guaranteed income|easy money|earn [$€£]?\d+ (?:per|a) day|"
        r"double your money|crypto signals|no skills required|без вложений|"
        r"гарантированный доход|легкие деньги|л[её]гкие деньги|доход от \d+ в день)\b",
    ),
    rule(
        ContentCategory.COURSE_OR_EDUCATION,
        "education:enrollment",
        8,
        r"\b(?:enroll now|join (?:our|the) (?:course|bootcamp|workshop|webinar)|"
        r"online course|paid mentorship|course starts|learn how to|регистрация на (?:курс|вебинар)|"
        r"записывайтесь на (?:курс|обучение|вебинар)|обучение с нуля|курс стартует|"
        r"менторская программа)\b",
    ),
    rule(
        ContentCategory.EVENT,
        "event:registration",
        7,
        r"\b(?:register for (?:the|our) (?:(?:\w+[ -]?){0,2})(?:conference|hackathon|meetup|event)|"
        r"conference tickets|hackathon registration|meetup starts|"
        r"регистрация на (?:конференцию|хакатон|митап|мероприятие)|"
        r"билеты на конференцию)\b",
    ),
    rule(
        ContentCategory.ADVERTISEMENT,
        "advertisement:promotion",
        7,
        r"\b(?:limited time offer|special offer|promo code|buy now|sale ends|"
        r"скидка до|акция до|промокод|успейте купить|специальное предложение)\b",
    ),
    rule(
        ContentCategory.COMMUNITY_POST,
        "community:editorial",
        6,
        r"\b(?:new article|read our guide|weekly digest|industry news|what do you think|"
        r"discussion thread|новая статья|читайте наш гайд|новости индустрии|"
        r"что вы думаете|обсудим в комментариях|полезный материал)\b",
    ),
)


FIRST_PERSON_IDENTITY_RE = re.compile(
    rf"\b(?:(?:i am|i m|i'm|я)\s+(?:an? |freelance )?{ROLE}|"
    rf"(?:меня зовут|my name is)\b.{{0,80}}\b{ROLE})\b",
    re.IGNORECASE,
)
PROFILE_LABEL_RE = re.compile(
    r"\b(?:portfolio|github|behance|dribbble|linkedin|resume|cv|портфолио|резюме)\b",
    re.IGNORECASE,
)
CONTACT_ME_RE = re.compile(
    r"\b(?:feel free to reach out|dm me|message me|contact me|пишите мне|связаться со мной)\b",
    re.IGNORECASE,
)
