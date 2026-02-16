"""
Offline AI marketing writer for GaboomDriveOS.
Generates campaign content from brief + templates + rules.
No external API required — pure template-based generation.
"""
import random
import re

# ═══════════════════════════════════════════════════════════════════════
# TEMPLATES — indexed by (objective, style, channel)
# ═══════════════════════════════════════════════════════════════════════

_TEMPLATES = {
    # ── PROMO ──────────────────────────────────────────────────────────
    ("promo", "luxe", "email"): [
        "Cher(e) {nom},\n\nNous avons le plaisir de vous offrir une opportunité exclusive : {offre}.\n\nRéservez dès maintenant votre {voiture} et vivez une expérience de conduite d'exception avec {agence}.\n\n{lien}\n\nCordialement,\nL'équipe {agence}",
        "Bonjour {nom},\n\nVotre fidélité mérite une récompense à la hauteur. Profitez de {offre} sur nos véhicules premium.\n\nDécouvrez notre sélection exclusive et réservez votre prochaine {voiture}.\n\n{lien}\n\nÀ très bientôt,\n{agence}",
    ],
    ("promo", "luxe", "whatsapp"): [
        "Bonjour {nom} ✨\nOffre exclusive {agence} : {offre}\nRéservez votre {voiture} :\n{lien}",
        "{nom}, une offre premium vous attend : {offre} sur nos véhicules d'exception.\n{lien}",
    ],
    ("promo", "luxe", "sms"): [
        "{agence}: {offre} sur votre prochaine location. Réservez: {lien}",
        "Offre VIP {agence}: {offre}. {lien}",
    ],
    ("promo", "simple", "email"): [
        "Bonjour {nom},\n\nBonne nouvelle ! Profitez de {offre} chez {agence}.\n\nRéservez maintenant : {lien}\n\nÀ bientôt !",
        "Salut {nom},\n\n{offre} sur nos véhicules, ça vous dit ?\n\nCliquez ici pour en profiter : {lien}\n\n{agence}",
    ],
    ("promo", "simple", "whatsapp"): [
        "Salut {nom} 👋\n{offre} chez {agence} !\nRéservez ici : {lien}",
        "Hey {nom} ! Promo en cours : {offre}. {lien}",
    ],
    ("promo", "simple", "sms"): [
        "{agence}: {offre}. Réservez: {lien}",
        "Promo {agence}: {offre} {lien}",
    ],
    ("promo", "urgent", "email"): [
        "⚡ {nom}, DERNIÈRES HEURES !\n\n{offre} — cette offre expire très bientôt.\n\nNe manquez pas cette occasion unique chez {agence}.\n\nRéservez MAINTENANT : {lien}",
        "🚨 ALERTE PROMO — {nom}\n\n{offre} disponible pour une durée limitée seulement !\n\nDépêchez-vous : {lien}\n\n{agence}",
    ],
    ("promo", "urgent", "whatsapp"): [
        "⚡ {nom} ! Dernière chance : {offre}\nRéservez vite : {lien}",
        "🚨 {offre} expire bientôt ! {lien}",
    ],
    ("promo", "urgent", "sms"): [
        "URGENT {agence}: {offre} expire! {lien}",
        "⚡{offre} dernières heures! {lien}",
    ],
    ("promo", "fun", "email"): [
        "Hey {nom} ! 🎉\n\nDevinez quoi ? {offre} chez {agence} !\n\nOn vous a gardé la meilleure place au volant 🚗\n\nFoncez : {lien}\n\nÀ fond la caisse ! 🏎️",
        "Yo {nom} ! 😎\n\n{offre} — oui oui, vous avez bien lu !\n\nVotre {voiture} vous attend chez {agence}.\n\n{lien}",
    ],
    ("promo", "fun", "whatsapp"): [
        "Hey {nom} 🎉 {offre} chez {agence} ! Foncez 🚗 {lien}",
        "{nom} 😎 Promo folle : {offre} ! {lien}",
    ],
    ("promo", "fun", "sms"): [
        "🎉{agence}: {offre}! Foncez: {lien}",
        "😎 {offre} chez {agence}! {lien}",
    ],
    ("promo", "corporate", "email"): [
        "Madame, Monsieur {nom},\n\nNous avons le plaisir de vous informer d'une offre spéciale : {offre}.\n\nNous vous invitons à découvrir nos services sur {lien}.\n\nRespectueux salutations,\n{agence}",
        "Bonjour {nom},\n\nDans le cadre de notre programme de fidélité, nous vous proposons : {offre}.\n\nPour en bénéficier : {lien}\n\nCordialement,\n{agence}",
    ],
    ("promo", "corporate", "whatsapp"): [
        "Bonjour {nom}. {agence} vous propose : {offre}. Détails : {lien}",
        "{nom}, offre professionnelle {agence} : {offre}. {lien}",
    ],
    ("promo", "corporate", "sms"): [
        "{agence}: Offre pro {offre}. {lien}",
        "{nom}, {offre} disponible. {lien}",
    ],

    # ── LANCEMENT ──────────────────────────────────────────────────────
    ("lancement", "luxe", "email"): [
        "Cher(e) {nom},\n\nNous sommes ravis de vous présenter notre dernière acquisition : la {voiture}.\n\nUn véhicule d'exception, disponible dès maintenant chez {agence}.\n\n{offre}\n\nDécouvrez-la : {lien}\n\nL'équipe {agence}",
        "Bonjour {nom},\n\nLa {voiture} rejoint notre flotte premium. Soyez parmi les premiers à la conduire.\n\n{offre}\n\n{lien}\n\n{agence}",
    ],
    ("lancement", "luxe", "whatsapp"): [
        "✨ {nom}, découvrez la {voiture} chez {agence} ! {offre}\n{lien}",
        "Nouveau : {voiture} disponible ! {offre} {lien}",
    ],
    ("lancement", "luxe", "sms"): [
        "Nouveau {agence}: {voiture} dispo! {offre} {lien}",
        "{voiture} disponible chez {agence}. {lien}",
    ],
    ("lancement", "simple", "email"): [
        "Bonjour {nom},\n\nNouveau véhicule disponible : {voiture} !\n\n{offre}\n\nRéservez : {lien}\n\n{agence}",
        "Salut {nom},\n\nLa {voiture} est arrivée chez {agence} ! {offre}\n\n{lien}",
    ],
    ("lancement", "simple", "whatsapp"): [
        "Salut {nom} 🚗 Nouveau : {voiture} dispo ! {offre} {lien}",
        "Hey ! {voiture} disponible chez {agence}. {lien}",
    ],
    ("lancement", "simple", "sms"): [
        "Nouveau: {voiture} chez {agence}! {lien}",
        "{voiture} dispo! {offre} {lien}",
    ],
    ("lancement", "fun", "email"): [
        "🚀 {nom} !\n\nLa {voiture} vient d'atterrir chez {agence} !\n\n{offre}\n\nSoyez le premier au volant : {lien}\n\n🏎️ Vrooom !",
    ],
    ("lancement", "fun", "whatsapp"): [
        "🚀 {nom} ! La {voiture} est là ! {offre} {lien}",
    ],
    ("lancement", "fun", "sms"): [
        "🚀{voiture} dispo! {offre} {lien}",
    ],
    ("lancement", "urgent", "email"): [
        "⚡ {nom},\n\nLa {voiture} est disponible en EXCLUSIVITÉ chez {agence} !\n\nPlaces limitées — {offre}\n\nRéservez immédiatement : {lien}",
    ],
    ("lancement", "urgent", "whatsapp"): [
        "⚡ {voiture} dispo en exclu ! {offre} Vite : {lien}",
    ],
    ("lancement", "urgent", "sms"): [
        "⚡{voiture} exclu! {offre} {lien}",
    ],
    ("lancement", "corporate", "email"): [
        "Bonjour {nom},\n\nNous avons le plaisir de vous annoncer l'arrivée de la {voiture} dans notre flotte.\n\n{offre}\n\nPlus d'informations : {lien}\n\nCordialement,\n{agence}",
    ],
    ("lancement", "corporate", "whatsapp"): [
        "Bonjour {nom}. Nouveau véhicule {voiture} disponible. {offre} {lien}",
    ],
    ("lancement", "corporate", "sms"): [
        "{agence}: {voiture} disponible. {lien}",
    ],

    # ── RELANCE ────────────────────────────────────────────────────────
    ("relance", "luxe", "email"): [
        "Cher(e) {nom},\n\nVous nous manquez ! Cela fait un moment que nous n'avons pas eu le plaisir de vous servir.\n\nRevenez découvrir nos nouveautés chez {agence}. {offre}\n\n{lien}\n\nAu plaisir,\n{agence}",
    ],
    ("relance", "luxe", "whatsapp"): [
        "{nom}, vous nous manquez ✨ {offre} pour votre retour ! {lien}",
    ],
    ("relance", "luxe", "sms"): [
        "{agence}: Vous nous manquez! {offre} {lien}",
    ],
    ("relance", "simple", "email"): [
        "Bonjour {nom},\n\nÇa fait un moment ! On a de belles offres pour vous : {offre}\n\nRevenez nous voir : {lien}\n\n{agence}",
    ],
    ("relance", "simple", "whatsapp"): [
        "Salut {nom} 👋 Ça fait longtemps ! {offre} {lien}",
    ],
    ("relance", "simple", "sms"): [
        "{nom}, revenez! {offre} {lien}",
    ],
    ("relance", "urgent", "email"): [
        "⚡ {nom}, ne ratez pas ça !\n\n{offre} — offre de retour exclusive, durée limitée.\n\n{lien}\n\n{agence}",
    ],
    ("relance", "urgent", "whatsapp"): [
        "⚡ {nom} ! Offre de retour : {offre} {lien}",
    ],
    ("relance", "urgent", "sms"): [
        "⚡Revenez! {offre} {lien}",
    ],
    ("relance", "fun", "email"): [
        "Hey {nom} ! 😢\n\nOn s'ennuie sans vous chez {agence} !\n\nPour fêter vos retrouvailles : {offre}\n\n{lien}\n\n🚗💨",
    ],
    ("relance", "fun", "whatsapp"): [
        "Hey {nom} 😢 On s'ennuie sans vous ! {offre} {lien}",
    ],
    ("relance", "fun", "sms"): [
        "😢 Revenez {nom}! {offre} {lien}",
    ],
    ("relance", "corporate", "email"): [
        "Bonjour {nom},\n\nNous souhaitons vous informer de nos dernières offres : {offre}.\n\nNous serions ravis de vous accueillir à nouveau.\n\n{lien}\n\nCordialement,\n{agence}",
    ],
    ("relance", "corporate", "whatsapp"): [
        "Bonjour {nom}. {agence} vous propose : {offre}. {lien}",
    ],
    ("relance", "corporate", "sms"): [
        "{agence}: {offre} pour vous. {lien}",
    ],

    # ── FIDELISATION ───────────────────────────────────────────────────
    ("fidelisation", "luxe", "email"): [
        "Cher(e) {nom},\n\nVotre fidélité est précieuse pour {agence}. En remerciement : {offre}.\n\nNous espérons vous revoir très bientôt.\n\n{lien}\n\nChaleureusement,\n{agence}",
    ],
    ("fidelisation", "luxe", "whatsapp"): [
        "{nom} ✨ Merci pour votre fidélité ! Cadeau : {offre} {lien}",
    ],
    ("fidelisation", "luxe", "sms"): [
        "Merci {nom}! Cadeau fidélité: {offre} {lien}",
    ],
    ("fidelisation", "simple", "email"): [
        "Bonjour {nom},\n\nMerci d'être un client fidèle ! Voici un petit cadeau : {offre}\n\n{lien}\n\n{agence}",
    ],
    ("fidelisation", "simple", "whatsapp"): [
        "Merci {nom} 🙏 Cadeau fidélité : {offre} {lien}",
    ],
    ("fidelisation", "simple", "sms"): [
        "Merci {nom}! {offre} {lien}",
    ],
    ("fidelisation", "fun", "email"): [
        "🎁 {nom} !\n\nVous êtes au top ! Pour vous remercier : {offre}\n\nOn vous adore chez {agence} ❤️\n\n{lien}",
    ],
    ("fidelisation", "fun", "whatsapp"): [
        "🎁 {nom} ! Cadeau pour vous : {offre} ❤️ {lien}",
    ],
    ("fidelisation", "fun", "sms"): [
        "🎁{nom} cadeau: {offre} {lien}",
    ],
    ("fidelisation", "urgent", "email"): [
        "{nom},\n\nVotre récompense fidélité expire bientôt : {offre}\n\nUtilisez-la avant qu'il ne soit trop tard !\n\n{lien}\n\n{agence}",
    ],
    ("fidelisation", "urgent", "whatsapp"): [
        "⚡ {nom} ! Votre cadeau expire : {offre} {lien}",
    ],
    ("fidelisation", "urgent", "sms"): [
        "⚡Cadeau expire! {offre} {lien}",
    ],
    ("fidelisation", "corporate", "email"): [
        "Bonjour {nom},\n\nEn reconnaissance de votre fidélité, {agence} vous offre : {offre}.\n\n{lien}\n\nCordialement,\n{agence}",
    ],
    ("fidelisation", "corporate", "whatsapp"): [
        "Bonjour {nom}. Récompense fidélité {agence} : {offre}. {lien}",
    ],
    ("fidelisation", "corporate", "sms"): [
        "{agence}: Fidélité {offre}. {lien}",
    ],

    # ── AVIS CLIENT ────────────────────────────────────────────────────
    ("avis", "luxe", "email"): [
        "Cher(e) {nom},\n\nNous espérons que votre expérience avec {agence} a été à la hauteur de vos attentes.\n\nVotre avis compte énormément pour nous. Pourriez-vous prendre un instant pour nous laisser votre retour ?\n\n{lien}\n\nMerci infiniment,\n{agence}",
    ],
    ("avis", "luxe", "whatsapp"): [
        "{nom}, votre avis compte ✨ Partagez votre expérience {agence} : {lien}",
    ],
    ("avis", "luxe", "sms"): [
        "{agence}: Votre avis compte! {lien}",
    ],
    ("avis", "simple", "email"): [
        "Bonjour {nom},\n\nComment s'est passée votre location ? On aimerait avoir votre avis !\n\n{lien}\n\nMerci !\n{agence}",
    ],
    ("avis", "simple", "whatsapp"): [
        "Salut {nom} ! Comment ça s'est passé ? Donnez-nous votre avis : {lien}",
    ],
    ("avis", "simple", "sms"): [
        "{nom}, votre avis? {lien}",
    ],
    ("avis", "fun", "email"): [
        "Hey {nom} ! 🌟\n\nAlors, cette balade en {voiture} ? On veut tout savoir !\n\nLaissez-nous un petit mot : {lien}\n\n{agence} 🚗💨",
    ],
    ("avis", "fun", "whatsapp"): [
        "Hey {nom} 🌟 Alors cette location ? Dites-nous tout : {lien}",
    ],
    ("avis", "fun", "sms"): [
        "🌟{nom} votre avis? {lien}",
    ],
    ("avis", "urgent", "email"): [
        "{nom},\n\nVotre avis nous aiderait beaucoup ! Cela ne prend que 30 secondes.\n\n{lien}\n\nMerci d'avance,\n{agence}",
    ],
    ("avis", "urgent", "whatsapp"): [
        "{nom}, 30 sec pour nous aider ! Votre avis : {lien}",
    ],
    ("avis", "urgent", "sms"): [
        "30sec: votre avis {agence} {lien}",
    ],
    ("avis", "corporate", "email"): [
        "Bonjour {nom},\n\nNous vous serions reconnaissants de bien vouloir partager votre retour d'expérience.\n\n{lien}\n\nCordialement,\n{agence}",
    ],
    ("avis", "corporate", "whatsapp"): [
        "Bonjour {nom}. Merci de partager votre avis sur {agence} : {lien}",
    ],
    ("avis", "corporate", "sms"): [
        "{agence}: Votre retour svp {lien}",
    ],
}

# ═══════════════════════════════════════════════════════════════════════
# REWRITE RULES
# ═══════════════════════════════════════════════════════════════════════

_EMOJI_MAP = {
    "voiture": "🚗", "offre": "🎁", "promo": "🔥", "réserv": "📅",
    "merci": "🙏", "bonjour": "👋", "exclu": "✨", "nouveau": "🆕",
    "urgent": "⚡", "dernière": "⏰", "fidél": "❤️", "avis": "⭐",
}

_LUXURY_WORDS = {
    "voiture": "véhicule d'exception",
    "offre": "privilège exclusif",
    "promo": "avantage premium",
    "réservez": "réservez votre expérience",
    "profitez": "laissez-vous séduire par",
    "salut": "Cher(e)",
    "hey": "Cher(e)",
}


def _add_emojis(text: str) -> str:
    """Insert contextual emojis into text."""
    result = text
    for keyword, emoji in _EMOJI_MAP.items():
        pattern = re.compile(rf'(\b\w*{keyword}\w*)', re.IGNORECASE)
        match = pattern.search(result)
        if match and emoji not in result:
            pos = match.end()
            result = result[:pos] + " " + emoji + result[pos:]
    return result


def _remove_emojis(text: str) -> str:
    """Strip emoji characters from text."""
    return re.sub(
        r'[\U0001F300-\U0001F9FF\u2600-\u26FF\u2700-\u27BF\u200d\uFE0F]',
        '', text
    ).replace('  ', ' ').strip()


def _make_shorter(text: str) -> str:
    """Shorten text by removing filler phrases and trimming."""
    removals = [
        r"Nous avons le plaisir de ",
        r"Nous sommes ravis de ",
        r"Nous souhaitons ",
        r"Nous vous invitons à ",
        r"Nous serions ravis de ",
        r"Cela ne prend que ",
        r"En reconnaissance de ",
        r"Dans le cadre de notre programme de fidélité, ",
        r"Nous espérons que votre expérience .+? a été à la hauteur de vos attentes\.\n\n",
    ]
    result = text
    for pattern in removals:
        result = re.sub(pattern, "", result, flags=re.IGNORECASE)
    lines = [line for line in result.split("\n") if line.strip()]
    return "\n".join(lines)


def _make_persuasive(text: str) -> str:
    """Add persuasive elements."""
    additions = [
        "\n\n💡 Les places partent vite — ne manquez pas cette occasion !",
        "\n\n🏆 Rejoignez nos clients satisfaits qui ont déjà profité de cette offre.",
        "\n\n⏰ Offre limitée — agissez maintenant pour en bénéficier.",
    ]
    if "limitée" not in text.lower() and "manquez" not in text.lower():
        text += random.choice(additions)
    return text


def _make_luxury(text: str) -> str:
    """Elevate tone to luxury."""
    result = text
    for word, replacement in _LUXURY_WORDS.items():
        result = re.sub(
            rf'\b{word}\b', replacement, result, count=1, flags=re.IGNORECASE
        )
    return result


# ═══════════════════════════════════════════════════════════════════════
# PUBLIC API
# ═══════════════════════════════════════════════════════════════════════

OBJECTIVES = [
    ("promo", "Promo"),
    ("lancement", "Lancement"),
    ("relance", "Relance"),
    ("fidelisation", "Fidélisation"),
    ("avis", "Avis client"),
]

STYLES = [
    ("luxe", "Luxe"),
    ("simple", "Simple"),
    ("urgent", "Urgent"),
    ("fun", "Fun"),
    ("corporate", "Corporate"),
]

CHANNELS = [
    ("email", "Email"),
    ("whatsapp", "WhatsApp"),
]

VARIABLES = ["{nom}", "{agence}", "{ville}", "{voiture}", "{prix}", "{lien}"]


def generate_message(
    objective: str,
    style: str,
    channel: str,
    offre: str = "",
    voiture: str = "",
    cta_link: str = "",
    agence: str = "",
    emojis: bool = True,
) -> str:
    """Generate a marketing message from brief parameters."""
    key = (objective, style, channel)
    templates = _TEMPLATES.get(key)

    if not templates:
        fallback_keys = [k for k in _TEMPLATES if k[0] == objective and k[2] == channel]
        if fallback_keys:
            templates = _TEMPLATES[random.choice(fallback_keys)]
        else:
            fallback_keys = [k for k in _TEMPLATES if k[0] == objective]
            if fallback_keys:
                templates = _TEMPLATES[random.choice(fallback_keys)]
            else:
                templates = list(_TEMPLATES.values())[0]

    template = random.choice(templates)

    result = template.replace("{offre}", offre or "notre offre spéciale")
    result = result.replace("{voiture}", voiture or "votre véhicule")
    result = result.replace("{lien}", cta_link or "https://votre-lien.com")
    result = result.replace("{agence}", agence or "{agence}")
    result = result.replace("{nom}", "{nom}")
    result = result.replace("{ville}", "{ville}")
    result = result.replace("{prix}", "{prix}")

    if not emojis:
        result = _remove_emojis(result)

    return result


def rewrite_message(mode: str, text: str, emojis: bool = True) -> str:
    """Rewrite existing text with a specific transformation."""
    if mode == "shorter":
        return _make_shorter(text)
    elif mode == "persuasive":
        return _make_persuasive(text)
    elif mode == "luxury":
        return _make_luxury(text)
    elif mode == "emojis_on":
        return _add_emojis(text)
    elif mode == "emojis_off":
        return _remove_emojis(text)
    elif mode == "improve":
        result = _make_persuasive(text)
        if emojis:
            result = _add_emojis(result)
        return result
    return text
