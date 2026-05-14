#!/usr/bin/env python3
"""Scrape Point of Departure (Issue 95) reviews."""

import re
import json
import os

def strip_html(text):
    if not text:
        return ""
    text = re.sub(r'<br\s*/?>', ' ', text)
    text = re.sub(r'<p[^>]*>', ' PARASPLIT ', text)
    text = re.sub(r'</p>', '', text)
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'&amp;', '&', text)
    text = re.sub(r'&mdash;', '—', text)
    text = re.sub(r'&ndash;', '–', text)
    text = re.sub(r'&ldquo;', '"', text)
    text = re.sub(r'&rdquo;', '"', text)
    text = re.sub(r'&lsquo;', "'", text)
    text = re.sub(r'&rsquo;', "'", text)
    text = re.sub(r'&nbsp;', ' ', text)
    text = re.sub(r'&hellip;', '…', text)
    text = re.sub(r'&#\d+;', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def first_500(text):
    t = strip_html(text)
    result = t[:500].strip()
    # Fix any broken words at end
    if result and len(t) > 500 and not result.endswith((' ', '.', ',', '!', '?', '"', "'")):
        # Try to find a word boundary near end
        last_space = result.rfind(' ', -30)
        if last_space > 200:
            result = result[:last_space]
    return result

def is_non_music_text(artist, album):
    for kw in ['BLU-RAY', 'BLU RAY', '(UHD', 'VOD', 'DVD ', 'VIDEO', 'FILM', 'DOCUMENTARY']:
        if kw.lower() in (artist + ' ' + album).lower():
            return True
    return False

def make_excerpt(text):
    """Take a plain text paragraph and return first 500 chars."""
    raw = strip_html(text)
    return first_500(raw)

# ── Issue 95 (June 2026) content scraped via curl ─────────────────────────────
# All file modified dates are within 3-day window (2026-05-12 to 2026-05-14)
# pub_date per task instructions

site_id = "point_of_departure"
source  = "Point of Departure"
tags    = ["improvised music", "creative music", "jazz", "essays"]
pub_date = "2026-05-14"
pub_ts   = 1778792700

reviews = []

# ── 1. Lead review: Moment's Notice (PoD95MomentsNotice.html) ─────────────────
# Julius Hemphill – Dogon A.D. (New World 80850-2) – reviewer: Kevin Whitehead
# Type: review (standard music review)

lead_artist = "Julius Hemphill"
lead_album  = "Dogon A.D."
lead_label  = "New World 80850-2"
lead_url    = "https://pointofdeparture.org/PoD95/PoD95MomentsNotice.html"

lead_excerpt = (
    "Wadud's cello voice is prominent on Coon Bid'ness' choogling Skin 1 and Skin 2, "
    "but even with that album to whet a new Hemphill fan's appetite, Abdul's entrance "
    "at the top of Dogon's 15-minute opening/title track was a stunner. First time "
    "I heard it, 49 years ago, I fell in love with the album before Julius had sounded "
    "a note: Wadud's grinding one-bar bowed-dyads ostinato turned cello into a big "
    "Delta blues guitar. Wadud wasn't the first jazz cello player by a long shot, "
    "though earlier ones mostly treated it like a baby bass. Other improvising "
    "cellists cropped up in the 1970s -- Diedre Murray, David Eyges, Tristan "
    "Honsinger, Tom Cora, Ernst Reijseger -- with many more soon to come, but "
    "nobody brought earthy sensibility and downhome funk to intonation and frictive "
    "bowing like Wadud. Dogon's grinder riff nestled in the cracks in Philip Wilson's "
    "sparse 11/16 drums and cymbal tattoo. And then come the horns, alto and trumpet "
    "meled in unison, and occasional blue minor harmony, phrasing like a single entity "
    "-- the yoked horns of World Saxophone Quartet coming."
)

reviews.append({
    "album": lead_album,
    "artist": lead_artist,
    "score": None,
    "url": lead_url,
    "source": source,
    "pub_date": pub_date,
    "tags": tags,
    "excerpt": first_500(lead_excerpt),
    "site_id": site_id,
    "crawl_status": "success",
    "type": "review",
})

# ── 2. More Moments page 1 (PoD95MoreMoments.html) ────────────────────────────
# Multiple reviews – Troy Collins, except where noted
# File date: 2026-05-14

more_url = "https://pointofdeparture.org/PoD95/PoD95MoreMoments.html"

more_reviews = [
    {
        "artist": "Caleb Wheeler Curtis",
        "album": "Ritual",
        "label": "Chill Tone CT007",
        "reviewer": "Troy Collins",
        "excerpt": (
            "Multi-instrumentalist Caleb Wheeler Curtis has developed a reputation for "
            "restless curiosity, from the expansive sprawl of The True Story of Bears and "
            "the Invention of the Battery (Imani, 2024) to his work with collaborative "
            "ensembles like Ember and Walking Distance. On Ritual, he refines that breadth "
            "into a concentrated yet no less ambitious project which focuses on the "
            "process of communal music-making. Drawing on his command of stritch "
            "(the straight alto associated with Rahsaan Roland Kirk), soprano, sopranino, "
            "and trumpet, Curtis assembles a fluctuating ensemble to explore wide-ranging "
            "sonic terrain that encompasses both tradition and forward-thinking experimentation."
        ),
    },
    {
        "artist": "Gordon Grdina Nomad Trio",
        "album": "ASH",
        "label": "Attaboygirl ABG 13",
        "reviewer": "Troy Collins",
        "excerpt": (
            "Canadian composer, guitarist, and oud master Gordon Grdina presents a trio "
            "of releases -- ASH, Reza, and Turnpike -- on his Attaboygirl label, "
            "continuing a pattern of issuing albums in groupings that reflect a prolific "
            "output fueled by boundless artistic curiosity. ASH reunites Grdina with "
            "pianist Matt Mitchell and drummer Jim Black for a third outing that builds "
            "on the elaborate, energetic interplay of their previous work. The trio's "
            "language is rhythmically and harmonically complex, yet malleable, allowing "
            "pieces to stretch, fragment, and reunite with precision."
        ),
    },
    {
        "artist": "Qalandar",
        "album": "Reza",
        "label": "Attaboygirl ABG 10",
        "reviewer": "Troy Collins",
        "excerpt": (
            "With Reza, Grdina turns to Qalandar, a contemporary Persian ensemble rooted "
            "in classical traditions that embraces improvisation and modern composition. "
            "Recorded live, the album captures a veteran acoustic quintet that includes "
            "setar player Ali Razmi, drummer Kenton Loewen, and percussionist Hamin "
            "Honari. The performance also serves as a tribute to the late Reza Honari, "
            "a master of the kamancheh (a traditional Persian bowed spike fiddle), "
            "which imbues the music with poignant emotion."
        ),
    },
    {
        "artist": "Gordon Grdina + Russ Lossing",
        "album": "Turnpike",
        "label": "Attaboygirl ABG 12",
        "reviewer": "Troy Collins",
        "excerpt": (
            "Turnpike offers a more intimate but no less probing encounter, pairing "
            "Grdina with Russ Lossing in a rare oud and piano duo setting. Originating "
            "from an impromptu encore during a European quartet tour, the collaboration "
            "evolved into a repertoire of original compositions, spontaneous "
            "improvisations, and a piece by Paul Motian. The duo's relationship is "
            "characterized by patience, space, and subtlety."
        ),
    },
    {
        "artist": "The Messthetics and James Brandon Lewis",
        "album": "Deface the Currency",
        "label": "Impulse! 00602488348652",
        "reviewer": "Troy Collins",
        "excerpt": (
            "Boasting an album title inspired by the revolutionary actions of the Greek "
            "philosopher Diogenes, Deface the Currency finds tenor saxophonist James "
            "Brandon Lewis and The Messthetics strengthening a genre-defying, yet "
            "seemingly inevitable collaboration. Anchored by the former Fugazi rhythm "
            "section of bassist Joe Lally and drummer Brendan Canty, alongside virtuosic "
            "guitarist Anthony Pirog, the quartet builds on their self-titled 2024 "
            "Impulse! debut with the cohesion of a road-tested band."
        ),
    },
    {
        "artist": "Adam O'Farrill",
        "album": "ELEPHANT",
        "label": "Out Of Your Head OOYH 042",
        "reviewer": "Troy Collins",
        "excerpt": (
            "Trumpeter and composer Adam O'Farrill has imposing ancestry -- son of "
            "Arturo O'Farrill and grandson of Chico O'Farrill -- but ELEPHANT, his "
            "fifth album as a leader, makes clear that his artistic identity is his own. "
            "Leading a young, intuitive quartet with pianist Yvonne Rogers, bassist "
            "Walter Stinson, and drummer Russell Holzman, O'Farrill incorporates an "
            "array of influences -- post-bop, indie rock, electronica, and contemporary "
            "classical -- into a singularly original language."
        ),
    },
    {
        "artist": "Mike Westbrook",
        "album": "The Piano in the Room and the Blues",
        "label": "thingamajig 2503",
        "reviewer": "Bill Shoemaker",
        "excerpt": (
            "This collection of intimate piano solos was issued on Mike Westbrook's "
            "90th birthday, just prior to his passing, giving the eleven pieces an aura "
            "of famous last words, even though they were uttered twenty years ago. "
            "Additionally, solo playing was tertiary to Westbrook's legacy, overshadowed "
            "by 60 years of breakthrough long-form works like Marching Song and The "
            "Cortege, the community outreach of the Brass Band, and a slew of durable "
            "recordings by mid-sized and large ensembles."
        ),
    },
    {
        "artist": "Kenny Wheeler Sextet",
        "album": "What Was",
        "label": "False Walls fw19",
        "reviewer": "Bill Shoemaker",
        "excerpt": (
            "Evan Parker's psi label reflected the totality of his advocacy. Sessions "
            "led by forward-thinking modernists like Gerd Dudek, Ray Warleigh, and Kenny "
            "Wheeler, reflected a set of decades-old associations as important to Parker "
            "as any others. Representative of the wealth of material recorded for the "
            "label, What Was, Wheeler's 1995 session with Warleigh, Stan Sulzman, John "
            "Paracelli, Chris Laurence, and Tony Levin, suggests there is more that has "
            "yet to see the light of day."
        ),
    },
]

for r in more_reviews:
    if is_non_music_text(r["artist"], r["album"]):
        print(f"SKIP (non-music): {r['artist']} - {r['album']}")
        continue
    reviews.append({
        "album": r["album"],
        "artist": r["artist"],
        "score": None,
        "url": more_url,
        "source": source,
        "pub_date": pub_date,
        "tags": tags,
        "excerpt": first_500(r["excerpt"]),
        "site_id": site_id,
        "crawl_status": "success",
        "type": "review",
    })

# ── Feature: Book Cooks (PoD95Leroy.html) ────────────────────────────────────
# "Legends In Their Own Lunchtime: An Exploration Of The Canterbury Scene"
# by Aymeric Leroy – not a music review, it's a book excerpt – type=feature
# The article title goes in album, author in artist

feature_url = "https://pointofdeparture.org/PoD95/PoD95Leroy.html"
feature_excerpt = (
    "1970 -- April 10th, 1970 -- IBC Studios, London. Negotiations were now underway "
    "between Sean Murphy and several labels including Deram, CBS and Harvest, the EMI "
    "sub-label that had distributed Volume Two in the UK and already had Kevin Ayers "
    "in its stock. Soft Machine signed with CBS, but Third was self-financed, taken "
    "partly from studio sessions, but also from live recordings (Facelift) and edits "
    "and loops of tapes made by Mike Ratledge and Hugh Hopper at the home of Bob "
    "Woolford. What is problematic is that, as well as making the album an uncomfortable "
    "listen, its sub-par production lessens the claim, widely held at the time of its "
    "release, that Third represented musical state-of-the-art."
)

reviews.append({
    "album": "Legends In Their Own Lunchtime: An Exploration Of The Canterbury Scene",
    "artist": "Aymeric Leroy",
    "score": None,
    "url": feature_url,
    "source": source,
    "pub_date": pub_date,
    "tags": tags + ["book excerpt", "canterbury scene"],
    "excerpt": first_500(feature_excerpt),
    "site_id": site_id,
    "crawl_status": "success",
    "type": "feature",
})

# ── Output ────────────────────────────────────────────────────────────────────
out_path = "/home/liyifan/music-record/2026/05/2026-05-15/point_of_departure_reviews.json"
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(reviews, f, ensure_ascii=False, indent=2)

print(f"Total items: {len(reviews)}")
for r in reviews:
    print(f"  [{r['type']}] {r['artist']} -- {r['album']}")
print(f"\nWritten to: {out_path}")
