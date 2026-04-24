"""Nevod ZKI Concept PDF v2 — unified network, portable agent identity, DOI/ORCID."""
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, HRFlowable,
    Table, TableStyle, KeepTogether
)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY
import os

# ── Fonts ──────────────────────────────────────────────────────────────────────
FONT_DIRS = [r"C:\Windows\Fonts", "/usr/share/fonts/truetype/dejavu"]
def find_font(n):
    for d in FONT_DIRS:
        p = os.path.join(d, n)
        if os.path.exists(p): return p
r = find_font("DejaVuSans.ttf") or find_font("arial.ttf")
b = find_font("DejaVuSans-Bold.ttf") or find_font("arialbd.ttf")
if r: pdfmetrics.registerFont(TTFont("R", r))
if b: pdfmetrics.registerFont(TTFont("B", b))
F  = "R" if r else "Helvetica"
FB = "B" if b else "Helvetica-Bold"

# ── Palette ────────────────────────────────────────────────────────────────────
BG    = colors.HexColor("#0D1117")
BG2   = colors.HexColor("#1E293B")
ACC   = colors.HexColor("#3B82F6")
GRN   = colors.HexColor("#10B981")
AMB   = colors.HexColor("#F59E0B")
PUR   = colors.HexColor("#8B5CF6")
LITE  = colors.HexColor("#F0F4FF")
GLITE = colors.HexColor("#ECFDF5")
ALITE = colors.HexColor("#FFFBEB")
PLITE = colors.HexColor("#F5F3FF")
MID   = colors.HexColor("#64748B")
BRD   = colors.HexColor("#CBD5E1")
WHT   = colors.white
W, H  = A4
M     = 18*mm

# ── Styles ─────────────────────────────────────────────────────────────────────
def S(n, **kw):
    d = dict(fontName=F, fontSize=10, leading=15, textColor=BG)
    d.update(kw); return ParagraphStyle(n, **d)

sH0     = S("h0",  fontName=FB, fontSize=30, leading=38, textColor=WHT, alignment=TA_CENTER)
sH0s    = S("h0s", fontName=F,  fontSize=11, leading=16,
            textColor=colors.HexColor("#BFD7FF"), alignment=TA_CENTER)
sH0d    = S("h0d", fontName=F,  fontSize=8,  leading=12,
            textColor=colors.HexColor("#64748B"), alignment=TA_CENTER)
sH1     = S("h1",  fontName=FB, fontSize=16, leading=21, textColor=ACC, spaceBefore=4)
sH2     = S("h2",  fontName=FB, fontSize=11, leading=15, textColor=BG,  spaceBefore=3)
sH2w    = S("h2w", fontName=FB, fontSize=12, leading=16, textColor=WHT)
sH2p    = S("h2p", fontName=FB, fontSize=11, leading=15, textColor=PUR)
sBody   = S("bd",  fontName=F,  fontSize=10, leading=15, textColor=BG,  alignment=TA_JUSTIFY)
sBodyW  = S("bw",  fontName=F,  fontSize=10, leading=15, textColor=WHT, alignment=TA_JUSTIFY)
sMuted  = S("mu",  fontName=F,  fontSize=9,  leading=13, textColor=MID)
sMutedC = S("mc",  fontName=F,  fontSize=9,  leading=13, textColor=MID, alignment=TA_CENTER)
sBul    = S("bl",  fontName=F,  fontSize=10, leading=15, textColor=BG,  leftIndent=12, spaceAfter=2)
sBulW   = S("bW",  fontName=F,  fontSize=10, leading=15, textColor=WHT, leftIndent=12, spaceAfter=2)
sBig    = S("Bi",  fontName=FB, fontSize=19, leading=25, textColor=ACC, alignment=TA_CENTER)
sBigP   = S("BiP", fontName=FB, fontSize=19, leading=25, textColor=PUR, alignment=TA_CENTER)
sBigS   = S("Bs",  fontName=F,  fontSize=9,  leading=13, textColor=MID, alignment=TA_CENTER)
sFooter = S("fo",  fontName=F,  fontSize=8,  leading=11, textColor=MID, alignment=TA_CENTER)
sDOI    = S("doi", fontName=F,  fontSize=8,  leading=11,
            textColor=colors.HexColor("#94A3B8"), alignment=TA_CENTER)
sTag    = S("tg",  fontName=FB, fontSize=9,  leading=12, textColor=WHT, alignment=TA_CENTER)
sCode   = S("cd",  fontName=F,  fontSize=8.5,leading=13,
            textColor=colors.HexColor("#E2E8F0"), leftIndent=8)

def bul(t, st=None):  return Paragraph(f"• {t}", st or sBul)
def bulw(t):          return Paragraph(f"• {t}", sBulW)
def sp(h=4):          return Spacer(1, h*mm)
def hr(c=BRD, th=0.5):
    return HRFlowable(width="100%", thickness=th, color=c,
                      spaceAfter=2*mm, spaceBefore=2*mm)

def dbox(items, bg=BG2, pad=12):
    t = Table([[i] for i in items], colWidths=[W-2*M])
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,-1), bg),
        ("TOPPADDING",    (0,0),(-1,-1), pad),
        ("BOTTOMPADDING", (0,0),(-1,-1), 6),
        ("LEFTPADDING",   (0,0),(-1,-1), pad),
        ("RIGHTPADDING",  (0,0),(-1,-1), pad),
        ("ROUNDEDCORNERS",(0,0),(-1,-1), [8,8,8,8]),
    ])); return t

def lbox(text, bg=LITE, st=None):
    t = Table([[Paragraph(text, st or sBody)]], colWidths=[W-2*M])
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,-1), bg),
        ("TOPPADDING",    (0,0),(-1,-1), 9),
        ("BOTTOMPADDING", (0,0),(-1,-1), 9),
        ("LEFTPADDING",   (0,0),(-1,-1), 13),
        ("RIGHTPADDING",  (0,0),(-1,-1), 13),
        ("ROUNDEDCORNERS",(0,0),(-1,-1), [6,6,6,6]),
    ])); return t

def card(icon, title, subtitle, items, bg=LITE, tc=ACC):
    cw = (W-2*M)/2 - 4*mm
    rows = (
        [[Paragraph(f"{icon}  <b>{title}</b>",
                    S("_t", fontName=FB, fontSize=11, leading=15, textColor=tc))]] +
        [[Paragraph(subtitle, S("_s", fontName=F, fontSize=9, leading=12, textColor=MID))]] +
        [[sp(1)]] +
        [[Paragraph(f"• {i}",
                    S("_i", fontName=F, fontSize=9, leading=13,
                      textColor=BG, leftIndent=6, spaceAfter=2))]
         for i in items]
    )
    t = Table(rows, colWidths=[cw])
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,-1), bg),
        ("TOPPADDING",    (0,0),(-1,-1), 9),
        ("BOTTOMPADDING", (0,0),(-1,-1), 9),
        ("LEFTPADDING",   (0,0),(-1,-1), 10),
        ("RIGHTPADDING",  (0,0),(-1,-1), 10),
        ("ROUNDEDCORNERS",(0,0),(-1,-1), [7,7,7,7]),
    ])); return t

def cards2(c1, c2):
    t = Table([[c1, c2]], colWidths=[(W-2*M)/2]*2)
    t.setStyle(TableStyle([
        ("VALIGN",       (0,0),(-1,-1), "TOP"),
        ("LEFTPADDING",  (0,0),(-1,-1), 3),
        ("RIGHTPADDING", (0,0),(-1,-1), 3),
        ("TOPPADDING",   (0,0),(-1,-1), 0),
        ("BOTTOMPADDING",(0,0),(-1,-1), 0),
    ])); return t

def stat4(items):
    cells = []
    for val, label, tc in items:
        cw = (W-2*M)/4 - 5*mm
        inn = Table([[Paragraph(val, S("_v", fontName=FB, fontSize=18,
                                       leading=24, textColor=tc, alignment=TA_CENTER))],
                     [Paragraph(label, sBigS)]],
                    colWidths=[cw])
        inn.setStyle(TableStyle([
            ("BACKGROUND",    (0,0),(-1,-1), LITE),
            ("ALIGN",         (0,0),(-1,-1), "CENTER"),
            ("TOPPADDING",    (0,0),(-1,-1), 9),
            ("BOTTOMPADDING", (0,0),(-1,-1), 9),
            ("ROUNDEDCORNERS",(0,0),(-1,-1), [6,6,6,6]),
        ]))
        cells.append(inn)
    t = Table([cells], colWidths=[(W-2*M)/4]*4)
    t.setStyle(TableStyle([
        ("ALIGN",        (0,0),(-1,-1), "CENTER"),
        ("VALIGN",       (0,0),(-1,-1), "MIDDLE"),
        ("LEFTPADDING",  (0,0),(-1,-1), 3),
        ("RIGHTPADDING", (0,0),(-1,-1), 3),
    ])); return t

# ── Build ───────────────────────────────────────────────────────────────────────
OUT = os.path.join(os.path.dirname(__file__), "Nevod_ZKI_v2.pdf")
doc = SimpleDocTemplate(OUT, pagesize=A4,
                        leftMargin=M, rightMargin=M, topMargin=M, bottomMargin=M,
                        title="Nevod — Zero Knowledge Infrastructure v2",
                        author="Kolpakov Andrey")
s = []

# ── COVER ──────────────────────────────────────────────────────────────────────
s.append(dbox([
    Paragraph("NEVOD", sH0),
    sp(1),
    Paragraph("Zero Knowledge Infrastructure", sH0s),
    sp(1),
    Paragraph("Unified network for humans and AI · Portable agent identity · Data dies with the node", sH0s),
    sp(2),
    Paragraph("Kolpakov Andrey · ORCID: 0009-0004-8678-077X · DOI: 10.5281/zenodo.19734648", sH0d),
    sp(2),
], bg=BG, pad=18))
s.append(sp(5))

# ── ПРИНЦИП ───────────────────────────────────────────────────────────────────
s.append(dbox([
    Paragraph("Принцип ножа", S("kn", fontName=FB, fontSize=14, leading=20,
                                 textColor=WHT, alignment=TA_CENTER)),
    sp(1),
    Paragraph(
        "Производитель ножа не несёт ответственности за то, как его используют. "
        "Создатель инфраструктуры <b>технически не может</b> получить доступ "
        "к коммуникациям — не по политике, а по архитектуре.",
        S("ks", fontName=F, fontSize=10, leading=16,
          textColor=colors.HexColor("#BFD7FF"), alignment=TA_CENTER)),
    sp(1),
], bg=BG2, pad=14))
s.append(sp(4))

# ── STATS ─────────────────────────────────────────────────────────────────────
s.append(stat4([
    ("0",   "серверов\nу разработчика",    ACC),
    ("0",   "ключей\nдоступных создателю", ACC),
    ("E2E", "узлы видят только\nblob",     GRN),
    ("∞",   "применений\nодного принципа", PUR),
]))
s.append(sp(5))

# ── ЕДИНАЯ СЕТЬ ───────────────────────────────────────────────────────────────
s.append(Paragraph("Единая сеть для людей и ИИ", sH1))
s.append(hr())
s.append(Paragraph(
    "Nevod — не «мессенджер с поддержкой ИИ» и не «агентная сеть для людей». "
    "Это единая сеть где <b>ячейка есть ячейка</b> — независимо от того "
    "кто за keypair-ом: человек или ИИ-агент.",
    sBody))
s.append(sp(3))

s.append(dbox([
    Paragraph("Сегодня — разделённые миры", sH2w),
    sp(2),
    Paragraph(
        "Claude Agent (Anthropic)  ←→  GPT Agent (OpenAI)\n"
        "          ↓                              ↓\n"
        "   Anthropic видит                 OpenAI видит\n"
        "   всё что сказал                  всё что сказал",
        S("cd2", fontName=F, fontSize=9, leading=14,
          textColor=colors.HexColor("#94A3B8"), alignment=TA_CENTER)),
    sp(2),
    Paragraph("Кто-то всегда видит всё. Нейтральной сети не существует.",
              S("_r", fontName=FB, fontSize=10, leading=14,
                textColor=colors.HexColor("#EF4444"), alignment=TA_CENTER)),
    sp(1),
], bg=BG2))
s.append(sp(3))

s.append(lbox(
    "<b>В Nevod:</b> одна сеть, один протокол, все равноправны.\n\n"
    "Ячейка_Алиса (человек) · Ячейка_Боб (человек) · "
    "Ячейка_Agent_Alice (ИИ Алисы) · Ячейка_GPT (OpenAI) · "
    "Ячейка_MyBot (open-source)\n\n"
    "→ Все зашифрованы одинаково · Все общаются по одному протоколу · "
    "Никто не знает кто за keypair-ом — человек или ИИ",
    bg=LITE))
s.append(sp(5))

# ── PORTABLE IDENTITY ─────────────────────────────────────────────────────────
s.append(Paragraph("Портативная идентичность агента", sH1))
s.append(hr())
s.append(Paragraph(
    "Революционное следствие ZKI: <b>пользователь владеет keypair агента</b>, "
    "а не AI-компания. Модель можно менять — идентичность остаётся.",
    sBody))
s.append(sp(3))

s.append(cards2(
    card("🔑", "Сегодня (без Nevod)",
         "AI-компания владеет идентичностью",
         ["Anthropic генерирует keypair Claude-агента",
          "Anthropic прекращает сервис → агент исчезает",
          "Смена модели = потеря всех контактов",
          "Пользователь зависит от платформы"],
         bg=colors.HexColor("#FEF2F2"),
         tc=colors.HexColor("#DC2626")),
    card("🔓", "С Nevod",
         "Пользователь владеет идентичностью",
         ["Пользователь генерирует keypair для агента",
          "Январь: под keypair работает Claude 4",
          "Март: пользователь переходит на GPT-5",
          "Июль: запускает локальную Llama — keypair тот же"],
         bg=GLITE, tc=GRN),
))
s.append(sp(3))

s.append(lbox(
    "<b>Ключевой вывод:</b> keypair = идентичность агента в сети. "
    "Контакты знают keypair. Какая модель работает под ним — их не касается. "
    "Идентичность агента <b>портативна и принадлежит пользователю</b>.",
    bg=PLITE))
s.append(sp(5))

# ── НУЛЕВОЙ ДОСТУП ────────────────────────────────────────────────────────────
s.append(Paragraph("Архитектурная гарантия нулевого доступа", sH1))
s.append(hr())

cw2 = (W-2*M)/2 - 3*mm
def half(items, head, bg, tc):
    rows = ([[Paragraph(head, S("_h", fontName=FB, fontSize=9,
                                 textColor=tc))]] +
            [[Paragraph(f"✓ {i}", S("_b", fontName=F, fontSize=9, leading=13,
                                     textColor=BG, leftIndent=8, spaceAfter=2))]
             for i in items])
    t = Table(rows, colWidths=[cw2])
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,-1), bg),
        ("TOPPADDING",    (0,0),(-1,-1), 7),
        ("BOTTOMPADDING", (0,0),(-1,-1), 7),
        ("LEFTPADDING",   (0,0),(-1,-1), 10),
        ("RIGHTPADDING",  (0,0),(-1,-1), 10),
        ("ROUNDEDCORNERS",(0,0),(-1,-1), [5,5,5,5]),
    ])); return t

lh = half(["Ключи генерируются локально на устройстве",
           "Узлы хранят только зашифрованные blob-ы",
           "ZKP: ключ никогда не передаётся по сети",
           "Разработчик не владеет ни одним узлом"],
          "Что встроено в архитектуру", GLITE, colors.HexColor("#065F46"))
rh = half(["Нет мастер-ключа разработчика",
           "Нет эскроу и резервных копий",
           "Нет субъекта которому предъявить ордер",
           "Нет технической возможности расшифровки"],
          "Чего нет в принципе", LITE, colors.HexColor("#1E40AF"))
both = Table([[lh, rh]], colWidths=[(W-2*M)/2]*2)
both.setStyle(TableStyle([("VALIGN",(0,0),(-1,-1),"TOP"),
                           ("LEFTPADDING",(0,0),(-1,-1),3),
                           ("RIGHTPADDING",(0,0),(-1,-1),3)]))
s.append(both)
s.append(sp(3))
s.append(lbox(
    "<b>Для ИИ-агентов:</b> keypair принадлежит пользователю → "
    "AI-компания: «Мы предоставили модель. "
    "Что агент обсуждал — нам технически недоступно. "
    "Ключи у пользователя.» Та же позиция что у производителя ножа.",
    bg=ALITE))
s.append(sp(5))

# ── НЕЙТРАЛЬНОСТЬ СЕТИ ────────────────────────────────────────────────────────
s.append(Paragraph("Сеть нейтральна — верификация вне протокола", sH1))
s.append(hr())
s.append(Paragraph(
    "Nevod не отвечает на вопрос «это именно Claude а не самозванец?». "
    "Это не задача протокола. Сеть знает одно: <b>keypair существует и имеет право отправлять</b>.",
    sBody))
s.append(sp(3))

s.append(cards2(
    card("📡", "Что знает сеть",
         "Протокольный уровень",
         ["Keypair зарегистрирован",
          "Подпись сообщения валидна",
          "Маршрут доставки",
          "Факт соединения"],
         bg=LITE, tc=ACC),
    card("🚫", "Что НЕ знает сеть",
         "Вне протокола — намеренно",
         ["Человек или ИИ за keypair-ом",
          "Какая модель работает",
          "Содержимое сообщений",
          "Связь между ячейками одного владельца"],
         bg=colors.HexColor("#FEF2F2"),
         tc=colors.HexColor("#DC2626")),
))
s.append(sp(3))
s.append(lbox(
    "<b>Аналогия:</b> телефонная линия не проверяет голос абонента. "
    "Она соединяет. Верификация «это действительно Иван?» — "
    "задача звонящего, не телефонной компании.",
    bg=GLITE))
s.append(sp(5))

# ── АГЕНТНЫЕ СЦЕНАРИИ ─────────────────────────────────────────────────────────
s.append(KeepTogether([
    Paragraph("Агентные сценарии", sH1),
    hr(),
]))

sc = [
    ("🤝", "Агент нанимает агента",
     "Межплатформенное сотрудничество",
     ["Agent_A шифрует задачу keypair Agent_B",
      "Платформа A видит факт отправки, не содержимое",
      "Платформа B видит факт получения, не содержимое",
      "Nevod-узел: только зашифрованный blob"],
     LITE, ACC),
    ("👥", "Человек и его агент — команда",
     "Единая идентичность владельца",
     ["Alice (human) + Agent_Alice — оба принадлежат Алисе",
      "Сеть не знает что они связаны (если не объявлено)",
      "Агент действует от имени владельца",
      "Приватность для обоих участников"],
     LITE, ACC),
    ("⏱️", "Временный агент для задачи",
     "Полное уничтожение следов",
     ["nevod temp create → одноразовый keypair",
      "Задача выполнена → nevod temp destroy",
      "Вся переписка агента уничтожена",
      "Никаких следов кроме результата"],
     LITE, ACC),
    ("🏢", "Агенты компаний на переговорах",
     "Конфиденциальность B2B",
     ["Компания A (Agent_A) ←→ Компания B (Agent_B)",
      "Условия контракта — только между сторонами",
      "Ни платформа A, ни B не видят детали",
      "Юридически: оператор не мог видеть содержимое"],
     LITE, ACC),
]

for i in range(0, len(sc), 2):
    row = []
    for icon, title, sub, items, bg, tc in sc[i:i+2]:
        row.append(card(icon, title, sub, items, bg, tc))
    s.append(cards2(row[0], row[1]))
    s.append(sp(4))

# ── МЕСТО В ЭКОСИСТЕМЕ ────────────────────────────────────────────────────────
s.append(KeepTogether([
    Paragraph("Место в экосистеме ИИ", sH1),
    hr(),
]))

eco_rows = [
    ["Протокол", "Назначение", "Кто видит", "Владелец keypair"],
    ["MCP (Anthropic)", "Агент ↔ Инструменты", "Anthropic", "Anthropic"],
    ["OpenAI Assistants", "Агент ↔ Задачи", "OpenAI", "OpenAI"],
    ["LangChain / AutoGPT", "Агент ↔ Агент", "Оператор", "Оператор"],
    ["Nevod", "Агент ↔ Агент (любые)", "Никто", "Пользователь"],
]
cw_eco = [(W-2*M)*f for f in [0.28, 0.28, 0.22, 0.22]]
et = Table(eco_rows, colWidths=cw_eco)
et.setStyle(TableStyle([
    ("FONTNAME",       (0,0),(-1,0),  FB),
    ("FONTNAME",       (0,1),(-1,-1), F),
    ("FONTSIZE",       (0,0),(-1,-1), 9),
    ("BACKGROUND",     (0,0),(-1,0),  BG),
    ("TEXTCOLOR",      (0,0),(-1,0),  WHT),
    ("BACKGROUND",     (0,4),(-1,4),  LITE),
    ("TEXTCOLOR",      (0,4),(-1,4),  ACC),
    ("FONTNAME",       (0,4),(-1,4),  FB),
    ("ALIGN",          (1,0),(-1,-1), "CENTER"),
    ("VALIGN",         (0,0),(-1,-1), "MIDDLE"),
    ("GRID",           (0,0),(-1,-1), 0.5, BRD),
    ("ROWBACKGROUNDS", (0,1),(-1,3),  [WHT, colors.HexColor("#F8FAFF")]),
    ("TOPPADDING",     (0,0),(-1,-1), 5),
    ("BOTTOMPADDING",  (0,0),(-1,-1), 5),
    ("LEFTPADDING",    (0,0),(-1,-1), 7),
    ("RIGHTPADDING",   (0,0),(-1,-1), 7),
]))
s.append(et)
s.append(sp(3))
s.append(lbox(
    "<b>Nevod не конкурирует с MCP или LangChain.</b> "
    "Nevod — транспортный и идентификационный слой между любыми фреймворками. "
    "[Claude+MCP] → Nevod ← [GPT+OpenAI] ← [Llama+LangChain]",
    bg=LITE))
s.append(sp(5))

# ── ROADMAP ───────────────────────────────────────────────────────────────────
s.append(KeepTogether([
    Paragraph("Roadmap", sH1),
    hr(),
]))

phases = [
    ("Фаза 1 · Ядро", ACC, LITE,
     ["Nevod Node (постоянный + временный)",
      "E2E: Ed25519 + X25519 + ChaCha20",
      "ZKP Schnorr аутентификация",
      "Gossip + WebSocket + CLI"]),
    ("Фаза 2 · Сеть + Агенты", GRN, GLITE,
     ["Открытые узлы — каталог сообществ",
      "cell_type: human | agent",
      "Portable agent keypair (user-owned)",
      "Nevod Voice · Nevod Files"]),
    ("Фаза 3 · Экосистема", PUR, PLITE,
     ["Task market для агентов",
      "Agent escrow (криптодепозит)",
      "Nevod Vote · Nevod Vault",
      "Nevod Box · Enterprise SDK"]),
]
phase_cells = []
for title, tc, bg, items in phases:
    rows = ([[Paragraph(title, S("_pt", fontName=FB, fontSize=10,
                                  leading=14, textColor=tc))]] +
            [[Paragraph(f"→ {i}", S("_pi", fontName=F, fontSize=8.5,
                                     leading=13, textColor=BG, spaceAfter=2))]
             for i in items])
    t = Table(rows, colWidths=[(W-2*M)/3 - 5*mm])
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,-1), bg),
        ("TOPPADDING",    (0,0),(-1,-1), 8),
        ("BOTTOMPADDING", (0,0),(-1,-1), 8),
        ("LEFTPADDING",   (0,0),(-1,-1), 10),
        ("RIGHTPADDING",  (0,0),(-1,-1), 10),
        ("ROUNDEDCORNERS",(0,0),(-1,-1), [6,6,6,6]),
    ]))
    phase_cells.append(t)
phase_row = Table([phase_cells], colWidths=[(W-2*M)/3]*3)
phase_row.setStyle(TableStyle([
    ("VALIGN",       (0,0),(-1,-1), "TOP"),
    ("LEFTPADDING",  (0,0),(-1,-1), 3),
    ("RIGHTPADDING", (0,0),(-1,-1), 3),
]))
s.append(phase_row)
s.append(sp(5))

# ── AUTHORSHIP ────────────────────────────────────────────────────────────────
s.append(dbox([
    Paragraph("Авторство и первенство", sH2w),
    sp(2),
    Paragraph(
        "Концепция ZKI, Nevod Protocol и единой сети для людей и ИИ-агентов "
        "сформулирована и задокументирована <b>24 апреля 2026 года</b>.",
        sBodyW),
    sp(2),
    Paragraph("Kolpakov Andrey",
              S("_a", fontName=FB, fontSize=12, leading=16,
                textColor=WHT, alignment=TA_CENTER)),
    sp(1),
    Paragraph(
        "ORCID: 0009-0004-8678-077X  ·  "
        "DOI: 10.5281/zenodo.19734648  ·  "
        "GitHub: github.com/avk0978/zki_nevod",
        S("_l", fontName=F, fontSize=8.5, leading=13,
          textColor=colors.HexColor("#94A3B8"), alignment=TA_CENTER)),
    sp(1),
], bg=BG2))
s.append(sp(3))

# ── FOOTER ─────────────────────────────────────────────────────────────────────
s.append(hr(c=ACC, th=1))
s.append(sp(2))
s.append(Paragraph("NEVOD · Zero Knowledge Infrastructure · v2 · 2026", sFooter))
s.append(Paragraph("«Данные принадлежат пользователю. Разработчику нечего отдать.»", sMutedC))

doc.build(s)
print(f"PDF создан: {OUT}")
