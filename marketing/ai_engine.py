"""
Marketing Engine 2.0 — Local AI Engine
Template selection, message generation, rewriting, scoring, and suggestions.
Zero external API calls — everything runs offline with heuristics.
"""
import random
import re

# ═══════════════════════════ CONSTANTS ════════════════════════════════

OBJECTIVES = [
    ("promo", "Promotion"),
    ("relance", "Relance"),
    ("fidelisation", "Fidélisation"),
    ("avis", "Avis client"),
    ("lancement", "Lancement"),
]

STYLES = [
    ("simple", "Simple"),
    ("corporate", "Corporate"),
    ("urgent", "Urgent"),
    ("luxe", "Luxe"),
    ("ultra_premium", "Ultra Premium"),
]

CHANNELS = [
    ("email", "Email"),
    ("whatsapp", "WhatsApp"),
]

VARIABLES = ["{nom}", "{agence}", "{ville}", "{voiture}", "{prix}", "{lien}", "{offre}"]

# ═══════════════════════════ TEMPLATES DB ═════════════════════════════
# Key: (objective, style, channel) → list of template strings

_TEMPLATES = {
    # ── PROMO ──
    ("promo", "simple", "email"): [
        "Bonjour {nom},\n\nProfitez de {offre} chez {agence} !\n\nRéservez dès maintenant : {lien}\n\nÀ bientôt,\n{agence}",
        "Bonjour {nom},\n\nBonne nouvelle ! {offre} sur nos véhicules.\n\nCliquez ici pour en profiter : {lien}\n\n{agence}",
        "Bonjour {nom},\n\n{agence} vous offre {offre} sur votre prochaine location.\n\nRéservez maintenant : {lien}\n\nCordialement,\n{agence}",
    ],
    ("promo", "simple", "whatsapp"): [
        "Bonjour {nom} 👋\n\n🎉 {offre} chez {agence} !\n\nRéservez ici : {lien}",
        "Salut {nom} !\n\n🔥 Offre spéciale : {offre}\n\n👉 {lien}\n\n{agence}",
        "Hey {nom} ! {offre} en ce moment chez {agence} 🚗✨\n\nProfitez-en : {lien}",
    ],
    ("promo", "urgent", "email"): [
        "⚠️ {nom}, dernières heures !\n\n{offre} — offre limitée chez {agence}.\n\nNe manquez pas cette occasion : {lien}\n\nDépêchez-vous !",
        "🔴 URGENT — {nom}\n\n{offre} expire bientôt !\n\nRéservez maintenant avant qu'il ne soit trop tard : {lien}\n\n{agence}",
    ],
    ("promo", "urgent", "whatsapp"): [
        "⚠️ {nom} ! DERNIÈRE CHANCE\n\n{offre} expire aujourd'hui !\n\n👉 {lien}\n\n{agence}",
        "🔴 {nom}, plus que quelques heures !\n\n{offre} chez {agence}\n\nRéservez MAINTENANT : {lien}",
    ],
    ("promo", "luxe", "email"): [
        "Cher(e) {nom},\n\nNous avons le plaisir de vous proposer une offre exclusive : {offre}.\n\nDécouvrez notre sélection premium : {lien}\n\nAvec nos salutations distinguées,\n{agence}",
        "Cher(e) {nom},\n\n{agence} vous réserve un privilège exceptionnel : {offre}.\n\nVotre véhicule d'exception vous attend : {lien}\n\nCordialement,\n{agence}",
    ],
    ("promo", "luxe", "whatsapp"): [
        "Cher(e) {nom},\n\n✨ Offre exclusive {agence} : {offre}\n\nDécouvrez : {lien}",
        "Bonjour {nom},\n\n🌟 Privilège réservé : {offre}\n\nRéservez votre expérience : {lien}\n\n{agence}",
    ],
    ("promo", "ultra_premium", "email"): [
        "Cher(e) {nom},\n\nEn tant que client privilégié de {agence}, nous vous offrons en avant-première : {offre}.\n\nCette offre est strictement réservée à notre cercle VIP.\n\nDécouvrez votre sélection personnalisée : {lien}\n\nAvec toute notre considération,\n{agence} — L'excellence automobile",
        "Cher(e) {nom},\n\n{agence} a le privilège de vous présenter une opportunité unique.\n\n{offre} — une attention exclusive pour nos clients les plus fidèles.\n\nAccédez à votre espace VIP : {lien}\n\nVotre satisfaction est notre priorité absolue.\n\n{agence}",
    ],
    ("promo", "ultra_premium", "whatsapp"): [
        "Cher(e) {nom},\n\n🏆 Offre VIP exclusive\n\n{offre}\n\nRéservé aux clients privilégiés {agence}\n\n👉 {lien}",
    ],
    ("promo", "corporate", "email"): [
        "Bonjour {nom},\n\nNous souhaitons vous informer d'une offre spéciale : {offre}.\n\nPour en bénéficier, veuillez consulter notre plateforme : {lien}\n\nCordialement,\nL'équipe {agence}",
        "Madame, Monsieur {nom},\n\n{agence} a le plaisir de vous proposer : {offre}.\n\nConsultez les détails : {lien}\n\nBien cordialement,\n{agence}",
    ],

    # ── RELANCE ──
    ("relance", "simple", "email"): [
        "Bonjour {nom},\n\nVous nous manquez ! Cela fait un moment que nous ne vous avons pas vu chez {agence}.\n\nPour votre retour, profitez de {offre} : {lien}\n\nÀ très bientôt !",
        "Bonjour {nom},\n\nOn pense à vous chez {agence} ! Votre prochaine location vous attend.\n\nEn ce moment : {offre}\n\nRéservez : {lien}",
    ],
    ("relance", "simple", "whatsapp"): [
        "Bonjour {nom} 👋\n\nVous nous manquez chez {agence} !\n\nPour votre retour : {offre}\n\n👉 {lien}",
        "Salut {nom} ! Ça fait longtemps 😊\n\n{agence} vous offre {offre}\n\nRéservez : {lien}",
    ],
    ("relance", "urgent", "email"): [
        "⏰ {nom}, ne passez pas à côté !\n\n{offre} — valable uniquement cette semaine.\n\nRevenez chez {agence} : {lien}",
    ],
    ("relance", "luxe", "email"): [
        "Cher(e) {nom},\n\nVotre fidélité nous est précieuse. {agence} souhaite vous accueillir à nouveau avec une attention particulière : {offre}.\n\nRedécouvrez notre collection : {lien}\n\nChaleureusement,\n{agence}",
    ],
    ("relance", "ultra_premium", "email"): [
        "Cher(e) {nom},\n\nVotre absence se fait sentir au sein de notre cercle privilégié.\n\n{agence} vous réserve un retour d'exception : {offre}.\n\nVotre place VIP vous attend : {lien}\n\nAvec nos plus sincères salutations,\n{agence}",
    ],

    # ── FIDÉLISATION ──
    ("fidelisation", "simple", "email"): [
        "Bonjour {nom},\n\nMerci pour votre fidélité ! En tant que client {agence}, vous bénéficiez de {offre}.\n\nProfitez-en : {lien}\n\nMerci de votre confiance !",
        "Bonjour {nom},\n\n{agence} vous remercie ! Voici votre récompense fidélité : {offre}.\n\nRéservez : {lien}",
    ],
    ("fidelisation", "simple", "whatsapp"): [
        "Merci {nom} ! 🙏\n\nVotre fidélité chez {agence} est récompensée : {offre}\n\n👉 {lien}",
    ],
    ("fidelisation", "luxe", "email"): [
        "Cher(e) {nom},\n\nVotre fidélité est un honneur pour {agence}. En témoignage de notre gratitude : {offre}.\n\nAccédez à vos avantages exclusifs : {lien}\n\nAvec toute notre reconnaissance,\n{agence}",
    ],
    ("fidelisation", "ultra_premium", "email"): [
        "Cher(e) {nom},\n\nVotre loyauté envers {agence} mérite une reconnaissance à la hauteur de votre exigence.\n\nNous avons le privilège de vous offrir : {offre}.\n\nCette attention est réservée à nos clients les plus précieux.\n\nDécouvrez : {lien}\n\nAvec notre plus profond respect,\n{agence}",
    ],

    # ── AVIS ──
    ("avis", "simple", "email"): [
        "Bonjour {nom},\n\nComment s'est passée votre expérience avec {agence} ?\n\nVotre avis nous aide à nous améliorer. Partagez-le ici : {lien}\n\nMerci beaucoup !",
        "Bonjour {nom},\n\nMerci d'avoir choisi {agence} ! Nous aimerions connaître votre avis.\n\nÇa ne prend que 30 secondes : {lien}\n\nMerci !",
    ],
    ("avis", "simple", "whatsapp"): [
        "Bonjour {nom} 😊\n\nComment était votre location chez {agence} ?\n\nDonnez votre avis : {lien}\n\nMerci ! 🙏",
        "Salut {nom} ! Votre avis compte pour {agence} ⭐\n\n👉 {lien}",
    ],
    ("avis", "luxe", "email"): [
        "Cher(e) {nom},\n\nNous espérons que votre expérience avec {agence} a été à la hauteur de vos attentes.\n\nVotre retour nous est infiniment précieux : {lien}\n\nAvec nos remerciements,\n{agence}",
    ],

    # ── LANCEMENT ──
    ("lancement", "simple", "email"): [
        "Bonjour {nom},\n\n🚗 Nouveau chez {agence} : {voiture} !\n\n{offre}\n\nDécouvrez-le : {lien}\n\nÀ bientôt !",
        "Bonjour {nom},\n\nGrande nouvelle ! {agence} accueille {voiture} dans sa flotte.\n\nPour fêter ça : {offre}\n\nRéservez en premier : {lien}",
    ],
    ("lancement", "simple", "whatsapp"): [
        "🚗 {nom}, nouveau véhicule chez {agence} !\n\n{voiture} est disponible !\n\n{offre}\n\n👉 {lien}",
    ],
    ("lancement", "luxe", "email"): [
        "Cher(e) {nom},\n\n{agence} a l'honneur de vous présenter sa dernière acquisition : {voiture}.\n\nUn véhicule d'exception, à la hauteur de vos exigences.\n\nPour son lancement : {offre}\n\nDécouvrez : {lien}\n\nCordialement,\n{agence}",
    ],
    ("lancement", "ultra_premium", "email"): [
        "Cher(e) {nom},\n\n{agence} dévoile en exclusivité : {voiture}.\n\nUne expérience de conduite inégalée, réservée à notre cercle VIP.\n\nPour célébrer ce lancement : {offre}.\n\nSoyez parmi les premiers : {lien}\n\nL'excellence n'attend pas.\n\n{agence}",
    ],
    ("lancement", "urgent", "whatsapp"): [
        "🔥 {nom} ! NOUVEAU : {voiture} chez {agence}\n\nDisponibilité limitée !\n\n{offre}\n\n👉 Réservez vite : {lien}",
    ],
}


# ═══════════════════════════ TEMPLATE SELECTION ═══════════════════════

def select_templates(objective, style, channel):
    """Return list of matching templates, with fallback."""
    key = (objective, style, channel)
    templates = _TEMPLATES.get(key)
    if templates:
        return templates

    # Fallback: same objective + channel, any style
    for k, v in _TEMPLATES.items():
        if k[0] == objective and k[2] == channel:
            return v

    # Fallback: same objective, any style/channel
    for k, v in _TEMPLATES.items():
        if k[0] == objective:
            return v

    # Last resort
    return list(_TEMPLATES.values())[0]


# ═══════════════════════════ GENERATE ═════════════════════════════════

def generate_message(
    objective="promo",
    style="simple",
    channel="email",
    offre="",
    voiture="",
    cta_link="",
    agence="",
    emojis=True,
):
    """Generate a marketing message from brief parameters."""
    templates = select_templates(objective, style, channel)
    template = random.choice(templates)

    result = template
    result = result.replace("{offre}", offre or "notre offre spéciale")
    result = result.replace("{voiture}", voiture or "votre véhicule")
    result = result.replace("{lien}", cta_link or "https://votre-lien.com")
    result = result.replace("{agence}", agence or "{agence}")

    if not emojis:
        result = _remove_emojis(result)

    return result


# ═══════════════════════════ REWRITE ══════════════════════════════════

def rewrite_message(mode, text, emojis=True):
    """Rewrite existing text with a specific transformation."""
    if mode == "shorter":
        return _make_shorter(text)
    elif mode == "persuasive":
        return _make_persuasive(text)
    elif mode == "luxury":
        return _make_luxury(text)
    elif mode == "urgent":
        return _make_urgent(text)
    elif mode == "improve":
        result = _make_persuasive(text)
        if emojis:
            result = _add_emojis(result)
        return result
    elif mode == "emojis_on":
        return _add_emojis(text)
    elif mode == "emojis_off":
        return _remove_emojis(text)
    return text


# ═══════════════════════════ SCORE (0-100) ════════════════════════════

def score_message(text):
    """Score a marketing message 0-100 with detailed breakdown."""
    scores = {}
    suggestions = []

    # 1. Personalisation (0-15)
    has_nom = "{nom}" in text
    has_agence = "{agence}" in text
    pers_score = 0
    if has_nom:
        pers_score += 10
    else:
        suggestions.append("Ajoutez {nom} pour personnaliser le message")
    if has_agence:
        pers_score += 5
    scores["personalisation"] = pers_score

    # 2. CTA / Link (0-20)
    has_link = "{lien}" in text or "http" in text.lower() or "lien" in text.lower()
    has_cta_word = any(w in text.lower() for w in [
        "réservez", "profitez", "découvrez", "cliquez", "commandez",
        "réserver", "profiter", "accédez", "consultez",
    ])
    cta_score = 0
    if has_link:
        cta_score += 12
    else:
        suggestions.append("Ajoutez un lien de réservation {lien}")
    if has_cta_word:
        cta_score += 8
    else:
        suggestions.append("Ajoutez un appel à l'action (ex: 'Réservez maintenant')")
    scores["cta"] = cta_score

    # 3. Length (0-15)
    length = len(text)
    if 100 <= length <= 600:
        len_score = 15
    elif 50 <= length < 100:
        len_score = 10
        suggestions.append("Le message est un peu court, ajoutez plus de détails")
    elif 600 < length <= 1000:
        len_score = 10
        suggestions.append("Le message est un peu long, essayez de raccourcir")
    elif length > 1000:
        len_score = 5
        suggestions.append("Message trop long — raccourcissez pour plus d'impact")
    else:
        len_score = 3
        suggestions.append("Message très court — ajoutez du contenu")
    scores["longueur"] = len_score

    # 4. Urgency (0-10)
    urgency_words = ["maintenant", "urgent", "dernière", "limité", "expire", "vite", "aujourd'hui", "dernières heures"]
    has_urgency = any(w in text.lower() for w in urgency_words)
    urg_score = 10 if has_urgency else 0
    if not has_urgency:
        suggestions.append("Ajoutez un sentiment d'urgence (ex: 'offre limitée')")
    scores["urgence"] = urg_score

    # 5. Clarity / structure (0-15)
    lines = [line for line in text.strip().split("\n") if line.strip()]
    has_greeting = any(text.lower().startswith(g) for g in ["bonjour", "cher", "salut", "hey", "madame", "monsieur"])
    has_signature = any(w in text.lower() for w in ["cordialement", "à bientôt", "merci", "l'équipe"])
    clarity_score = 0
    if has_greeting:
        clarity_score += 5
    else:
        suggestions.append("Commencez par une salutation personnalisée")
    if has_signature:
        clarity_score += 5
    else:
        suggestions.append("Ajoutez une signature ou formule de politesse")
    if len(lines) >= 3:
        clarity_score += 5
    else:
        suggestions.append("Structurez le message en plusieurs paragraphes")
    scores["clarté"] = clarity_score

    # 6. Benefit / value proposition (0-15)
    benefit_words = ["offre", "remise", "réduction", "gratuit", "cadeau", "bonus", "avantage", "privilège", "exclusif", "spécial"]
    has_benefit = any(w in text.lower() for w in benefit_words) or "{offre}" in text
    ben_score = 15 if has_benefit else 0
    if not has_benefit:
        suggestions.append("Mettez en avant un bénéfice concret (offre, remise, avantage)")
    scores["bénéfice"] = ben_score

    # 7. Scarcity / exclusivity (0-10)
    scarcity_words = ["exclusif", "réservé", "vip", "limité", "unique", "privilège", "avant-première", "cercle"]
    has_scarcity = any(w in text.lower() for w in scarcity_words)
    scar_score = 10 if has_scarcity else 0
    if not has_scarcity:
        suggestions.append("Ajoutez un élément de rareté (ex: 'offre exclusive', 'places limitées')")
    scores["rareté"] = scar_score

    total = sum(scores.values())

    return {
        "total": min(total, 100),
        "breakdown": scores,
        "suggestions": suggestions[:6],
        "grade": _grade(total),
    }


def _grade(score):
    if score >= 85:
        return "A"
    elif score >= 70:
        return "B"
    elif score >= 50:
        return "C"
    elif score >= 30:
        return "D"
    return "F"


def suggest_improvements(text):
    """Return a list of concrete improvement suggestions."""
    result = score_message(text)
    return result["suggestions"]


# ═══════════════════════════ REWRITE HELPERS ══════════════════════════

def _make_shorter(text):
    """Shorten text by removing filler and keeping essentials."""
    lines = text.strip().split("\n")
    kept = []
    filler = [
        "nous avons le plaisir", "nous souhaitons vous informer",
        "en tant que client", "votre fidélité nous est",
        "nous espérons que", "cette offre est strictement",
    ]
    for line in lines:
        low = line.lower().strip()
        if not low:
            continue
        if any(f in low for f in filler):
            continue
        kept.append(line)
    return "\n".join(kept) if kept else text


def _make_persuasive(text):
    """Add persuasive elements."""
    replacements = {
        "profitez de": "ne manquez surtout pas",
        "découvrez": "découvrez sans attendre",
        "réservez": "réservez dès maintenant",
        "offre spéciale": "offre exceptionnelle à durée limitée",
        "en ce moment": "en ce moment — places limitées",
        "votre prochaine": "votre prochaine (et meilleure)",
    }
    result = text
    for old, new in replacements.items():
        result = re.sub(re.escape(old), new, result, flags=re.IGNORECASE, count=1)
    return result


def _make_luxury(text):
    """Transform to luxury tone."""
    replacements = {
        "bonjour": "Cher(e)",
        "salut": "Cher(e)",
        "hey": "Cher(e)",
        "profitez": "bénéficiez de ce privilège exclusif",
        "offre": "attention personnalisée",
        "réservez": "accédez à votre expérience",
        "cliquez ici": "découvrez votre sélection",
        "à bientôt": "avec nos salutations les plus distinguées",
        "merci": "avec toute notre gratitude",
    }
    result = text
    for old, new in replacements.items():
        result = re.sub(re.escape(old), new, result, flags=re.IGNORECASE, count=1)
    return result


def _make_urgent(text):
    """Add urgency to the message."""
    replacements = {
        "profitez de": "⚠️ DERNIÈRE CHANCE — profitez de",
        "découvrez": "🔴 Découvrez MAINTENANT",
        "réservez": "⏰ Réservez IMMÉDIATEMENT",
        "offre spéciale": "offre FLASH — expire bientôt",
        "en ce moment": "AUJOURD'HUI SEULEMENT",
    }
    result = text
    for old, new in replacements.items():
        result = re.sub(re.escape(old), new, result, flags=re.IGNORECASE, count=1)
    return result


_EMOJI_PATTERN = re.compile(
    "["
    "\U0001F600-\U0001F64F"
    "\U0001F300-\U0001F5FF"
    "\U0001F680-\U0001F6FF"
    "\U0001F1E0-\U0001F1FF"
    "\U00002702-\U000027B0"
    "\U0001F900-\U0001F9FF"
    "\U00002600-\U000026FF"
    "\u200d\ufe0f"
    "⚠️🔴⏰🎉🔥👋😊🙏⭐👉🚗✨🏆🌟💎"
    "]+",
    flags=re.UNICODE,
)


def _remove_emojis(text):
    return _EMOJI_PATTERN.sub("", text).strip()


def _add_emojis(text):
    """Add contextual emojis."""
    mapping = {
        "bonjour": "👋 Bonjour",
        "offre": "🎉 offre",
        "réservez": "👉 Réservez",
        "merci": "🙏 Merci",
        "nouveau": "🚗 Nouveau",
        "exclusif": "✨ Exclusif",
        "urgent": "⚠️ Urgent",
    }
    result = text
    for word, replacement in mapping.items():
        if word in result.lower() and replacement.split(" ", 1)[-1] not in result:
            result = re.sub(
                re.escape(word), replacement, result,
                flags=re.IGNORECASE, count=1,
            )
    return result
