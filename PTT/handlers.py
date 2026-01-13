import regex

from PTT.adult import create_adult_pattern
from PTT.parse import Parser
from PTT.transformers import (
    array,
    boolean,
    concat_values,
    date,
    integer,
    lowercase,
    none,
    range_func,
    transform_resolution,
    uniq_concat,
    uppercase,
    value,
)

def handle_trash_after_markers(context):
    title = context["title"]
    # dopasuj sekwencję co najmniej trzech znaków z zestawu
    marker_pattern = r"[-_\|\[\]\{\}\(\)\.]{3,}"
    # znajdź wszystkie wystąpienia
    matches = list(regex.finditer(marker_pattern, title))
    if not matches:
        return None

    # weź ostatnie z nich
    last = matches[-1]
    start = last.start()
    length = len(last.group(0))
    cut_index = start + length  # tu zaczyna się to, co ma zostać usunięte

    raw = title[cut_index:]     # fragment do usunięcia
    return {
        "raw_match": raw,
        "match_index": cut_index,
        "remove": True
    }

def handle_site_before_title(context):
    text = context["title"]

    # wzorzec całej domeny z pl/com.pl, www. i wieloma poddomenami
    domain_pattern = (
        r'(?:www\.)?[\w-]+(?:\.[\w-]+)*'
        r'(?:\.(?:com\.)?pl|[\s-]pl|\.?yoyo\.pl)'
    )

    # 1) Bracketed: [domena.pl]  lub  {domena.com.pl}  albo  (domena pl)
    m = regex.search(
        rf'^[\(\[\{{]\s*'
        rf'({domain_pattern})'
        rf'\s*[\)\]\}}]\s*',    # zamknięcie nawiasu + ewentualne spacje
        text,
        regex.IGNORECASE
    )

    # 2) Bez nawiasu: tylko strona.pl / example.com.pl / www.strona.pl
    if not m:
        # prostszy wzorzec: dokładnie jedna etykieta + .pl (lub .com.pl)
        simple_domain = r'(?:www\.)?[\w-]+\.(?:com\.)?pl|(?:[\w-]+\.)?yoyo\.pl'
        # po domain musi być spacja lub '-' lub '_'
        m = regex.search(
            rf'^({simple_domain})(?:\s+|[-_])\s*',
            text,
            regex.IGNORECASE
        )
        if not m:
            return None

    raw        = m.group(0)        # np. "[Audio PL] " lub "best-torrents pl - "
    site_start = m.start()         # powinno być 0
    val        = m.group(1).strip()  # np. "Audio PL" lub "best-torrents pl"

    return {
        "raw_match": raw,
        "match_index": site_start,
        "remove": True,
        "value": val
    }


def add_defaults(parser: Parser):
    # ———————— PREPROCESSOR ————————  
    # Specjalny wzorzec: "The Office PL" lub "The.Office.PL"
    office_pl_pattern = regex.compile(
        r"(?i)(?<!\w)The[ .]Office[ .]PL(?!\w)"
    )

    original_parse = parser.parse

    def parse_wrapper(raw_title, *args, **kwargs):
        if not hasattr(parser, "context"):
            parser.context = {}
        # --- VERY FIRST THING: strip off the “[site] - ” (or “site - ”)
        pre = handle_site_before_title({"title": raw_title})
        if pre and pre["remove"]:
            parser.context["site"] = pre["value"]
            # only remove exactly what was matched, leaving underscores alone
            raw_title = raw_title[len(pre["raw_match"]):]
        
        cleaned = regex.sub(r'(?<=[\[\]])\s+', '', raw_title)
        parser.context["_skip_languages_until_title"] = True
        result = original_parse(cleaned, *args, **kwargs)

        # Fallback: jeśli tytuł zwinął się do samej liczby, a oryginał zaczyna się "NNNN Słowo(≥3)"
        # to odtwórz frazę od początku do pierwszego nawiasu/kwadratu/klamry.
        if isinstance(result.get("title"), str) and regex.fullmatch(r"\d{1,4}", result["title"].strip()):
            m = regex.match(
                r"^\s*(\d{1,4}\s+[A-Za-zĄĆĘŁŃÓŚŹŻąćęłńóśźż]{3}[^\[\]\(\)\{\}]*)",
                cleaned
            )
            if m:
                result["title"] = m.group(1).strip(" .-_")

        # >>> SPECJALNY WYJĄTEK DLA "The Office PL" <<<
        # Jeśli w surowym tytule jest "The Office PL" lub "The.Office.PL",
        # wymuszamy title = "The Office PL".
        # "PL" zostało już złapane przez handlery językowe → languages zawiera "pl".
        if office_pl_pattern.search(cleaned):
            result["title"] = "The Office PL"

        # 3) wgrywamy site do finalnego wyniku, jeśli mamy je w kontekście
        if "site" in parser.context:
            result["site"] = parser.context.pop("site")
        return result

    parser.parse = parse_wrapper
    
    """
    Adds default handlers to the provided parser for various patterns such as episode codes, resolution,
    date formats, year ranges, etc. The handlers use regular expressions to match patterns and transformers
    to process the matched values.

    :param parser: The parser instance to which handlers will be added.
    """
    # pre-hardcoded cleanup (yuck)
    parser.add_handler("title", regex.compile(r"360.Degrees.of.Vision.The.Byakugan'?s.Blind.Spot", regex.IGNORECASE), none, {"remove": True}) # episode title
    parser.add_handler("title", regex.compile(r"\b100[ .-]*years?[ .-]*quest\b", regex.IGNORECASE), none, {"remove": True})  # episode title
    parser.add_handler("title", regex.compile(r"\[?(\+.)?Extras\]?", regex.IGNORECASE), none, {"remove": True})

    # Container
    parser.add_handler("container", regex.compile(r"\.?[\[(]?\b(MKV|AVI|MP4|WMV|MPG|MPEG)\b[\])]?", regex.IGNORECASE), lowercase)

    # Torrent extension
    parser.add_handler("torrent", regex.compile(r"\.torrent$"), boolean, {"remove": True})

    # Adult
    parser.add_handler("adult", regex.compile(r"\b(?:xxx|xx)\b", regex.IGNORECASE), boolean, {"remove": True, "skipFromTitle": True})
    parser.add_handler("adult", create_adult_pattern(), boolean, {"remove": True, "skipFromTitle": True, "skipIfAlreadyFound": True})

    # Scene
    parser.add_handler("scene", regex.compile(r"^(?=.*(\b\d{3,4}p\b).*([_. ]WEB[_. ])(?!DL)\b)|\b(-CAKES|-GGEZ|-GGWP|-GLHF|-GOSSIP|-NAISU|-KOGI|-PECULATE|-SLOT|-EDITH|-ETHEL|-ELEANOR|-B2B|-SPAMnEGGS|-FTP|-DiRT|-SYNCOPY|-BAE|-SuccessfulCrab|-NHTFS|-SURCODE|-B0MBARDIERS)"), boolean, {"remove": False})

    # Extras (This stuff can be trashed)
    parser.add_handler("extras", regex.compile(r"\bNCED\b", regex.IGNORECASE), uniq_concat(value("NCED")), {"remove": True})
    parser.add_handler("extras", regex.compile(r"\bNCOP\b", regex.IGNORECASE), uniq_concat(value("NCOP")), {"remove": True})
    parser.add_handler("extras", regex.compile(r"\bNC\b", regex.IGNORECASE), uniq_concat(value("NC")), {"remove": True})
    parser.add_handler("extras", regex.compile(r"\bOVA\b", regex.IGNORECASE), uniq_concat(value("OVA")), {"remove": True})
    parser.add_handler("extras", regex.compile(r"\bED(\d?v?\d?)\b", regex.IGNORECASE), uniq_concat(value("ED")), {"remove": True})
    parser.add_handler("extras", regex.compile(r"\bOPv?(\d+)?\b", regex.IGNORECASE), uniq_concat(value("OP")), {"remove": True})
    parser.add_handler("extras", regex.compile(r"\b(?:Deleted[ .-]*)?Scene(?:s)?\b", regex.IGNORECASE), uniq_concat(value("Deleted Scene")), {"remove": False})
    parser.add_handler("extras", regex.compile(r"(?:(?<=\b(?:19\d{2}|20\d{2})\b.*)\b(?:Featurettes?)\b|\bFeaturettes?\b(?!.*\b(?:19\d{2}|20\d{2})\b))", regex.IGNORECASE), uniq_concat(value("Featurette")), {"skipFromTitle": True, "remove": False})
    parser.add_handler("extras", regex.compile(r"(?:(?<=\b(?:19\d{2}|20\d{2})\b.*)\b(?:Sample)\b|\b(?:Sample)\b(?!.*\b(?:19\d{2}|20\d{2})\b))", regex.IGNORECASE), uniq_concat(value("Sample")), {"skipFromTitle": True, "remove": False})
    parser.add_handler("extras", regex.compile(r"(?:(?<=\b(?:19\d{2}|20\d{2})\b.*)\b(?:Trailers?)\b|\bTrailers?\b(?!.*\b(?:19\d{2}|20\d{2}|.(Park|And))\b))", regex.IGNORECASE), uniq_concat(value("Trailer")), {"skipFromTitle": True, "remove": False})

    # PPV
    parser.add_handler("ppv", regex.compile(r"\bPPV\b", regex.IGNORECASE), boolean, {"skipFromTitle": True, "remove": True})
    parser.add_handler("ppv", regex.compile(r"\b\W?Fight.?Nights?\W?\b", regex.IGNORECASE), boolean, {"skipFromTitle": True, "remove": False})

    # Site before languages to get rid of domain name with country code.
    parser.add_handler("site", regex.compile(r"^(www?[., ][\w-]+[. ][\w-]+(?:[. ][\w-]+)?)\s+-\s*", regex.IGNORECASE), options={"skipFromTitle": True, "remove": True, "skipIfAlreadyFound": False})
    parser.add_handler("site", regex.compile(r"^((?:www?[\.,])?[\w-]+\.[\w-]+(?:\.[\w-]+)*?)\s+-\s*", regex.IGNORECASE), options={"skipIfAlreadyFound": False})
    parser.add_handler("site", regex.compile(r"\bwww.+rodeo\b", regex.IGNORECASE), lowercase, {"remove": True})

    # Resolution
    parser.add_handler("resolution", regex.compile(r"\[?\]?3840x\d{4}[\])?]?", regex.IGNORECASE), value("2160p"), {"remove": True})
    parser.add_handler("resolution", regex.compile(r"\[?\]?1920x\d{3,4}[\])?]?", regex.IGNORECASE), value("1080p"), {"remove": True})
    parser.add_handler("resolution", regex.compile(r"\[?\]?1280x\d{3}[\])?]?", regex.IGNORECASE), value("720p"), {"remove": True})
    parser.add_handler("resolution", regex.compile(r"\[?\]?(\d{3,4}x\d{3,4})[\])?]?p?", regex.IGNORECASE), value("$1p"), {"remove": True})
    parser.add_handler("resolution", regex.compile(r"(480|720|1080)0[pi]", regex.IGNORECASE), value("$1p"), {"remove": True})
    parser.add_handler("resolution", regex.compile(r"(?:QHD|QuadHD|WQHD|2560(\d+)?x(\d+)?1440p?)", regex.IGNORECASE), value("1440p"), {"remove": True})
    parser.add_handler("resolution", regex.compile(r"(?:Full HD|FHD|1920(\d+)?x(\d+)?1080p?)", regex.IGNORECASE), value("1080p"), {"remove": True})
    parser.add_handler("resolution", regex.compile(r"(?:BD|HD|M)(2160p?|4k)", regex.IGNORECASE), value("2160p"), {"remove": True})
    parser.add_handler("resolution", regex.compile(r"(?:BD|HD|M)1080p?", regex.IGNORECASE), value("1080p"), {"remove": True})
    parser.add_handler("resolution", regex.compile(r"(?:BD|HD|M)720p?", regex.IGNORECASE), value("720p"), {"remove": True})
    parser.add_handler("resolution", regex.compile(r"(?:BD|HD|M)480p?", regex.IGNORECASE), value("480p"), {"remove": True})
    parser.add_handler("resolution", regex.compile(r"\b(?:4k|2160p|1080p|720p|480p)(?!.*\b(?:4k|2160p|1080p|720p|480p)\b)", regex.IGNORECASE), transform_resolution, {"remove": True})
    parser.add_handler("resolution", regex.compile(r"\b4k|21600?[pi]\b", regex.IGNORECASE), value("2160p"), {"remove": True})
    parser.add_handler("resolution", regex.compile(r"(\d{3,4})[pi]", regex.IGNORECASE), value("$1p"), {"remove": True})
    parser.add_handler("resolution", regex.compile(r"(240|360|480|576|720|1080|2160|3840)[pi]", regex.IGNORECASE), lowercase, {"remove": True})

    # Episode code
    parser.add_handler("episode_code", regex.compile(r"[\[\()]([A-Za-f0-9]{8})[\]\)]"), uppercase, {"remove": True})
    parser.add_handler("episode_code", regex.compile(r"[\[\()]([0-9]{8})[\]\)]"), uppercase, {"remove": True, "skipIfAlreadyFound": True})

    # This one doesn't seem like its needed for all the test cases.
    # parser.add_handler("episode_code", regex.compile(r"(?:\[|\()(?=\D+\d|\d+[^\d\])])\b([A-Z0-9]{8}|[a-z0-9]{8})(?:\]|\))"), uppercase, {"remove": True, "skipIfAlreadyFound": True})


    parser.add_handler(
        "cleanup",
        regex.compile(
            r"\b(?:sub[ _.\-]?eng[ _.\-]?pl|sub[ _.\-]?pl|pl[ _.\-]?sub|pl[ _.\-]?subbed|plsub|plsubbed|subbedpl|napisypl)\b",
            regex.IGNORECASE
        ),
        boolean,
        {"remove": True}
    )
    parser.add_handler(
        "cleanup",
        regex.compile(r"\+\s*sub\s*[^+]*", regex.IGNORECASE),
        boolean,
        {"remove": True}
    )

    parser.add_handler(
        "cleanup",
        regex.compile(r"(?i)(?:[\[\(\{]\s*)?napisy[\s._\-]*ai[\s._\-]*pl(?:\s*[\]\)\}])?"),
        boolean,
        {"remove": True}
    )
    parser.add_handler(
        "cleanup",
        regex.compile(
            r"\bnapisy[\s._\-|\]\)\(\[\}\{]*multi[\s._\-|\]\)\(\[\}\{]*\d+[\s._\-|\]\)\(\[\}\{]*(?:pl|pol)\b",
            regex.IGNORECASE
        ),
        boolean,
        {"remove": True}
    )
    
    # Trash (Equivalent to RTN auto-trasher) - DO NOT REMOVE HERE!
    # This one is pretty strict, but it removes a lot of the garbage
    # parser.add_handler("trash", regex.compile(r"\b(\w+rip|hc|((h[dq]|clean)(.+)?)?cam.?(rip|rp)?|(h[dq])?(ts|tc)(?:\d{3,4})?|tele(sync|cine)?|\d+[0o]+([mg]b)|\d{3,4}tc)\b"), boolean, {"remove": False})
    parser.add_handler("trash", regex.compile(r"\b(?:H[DQ][ .-]*)?CAM(?!.?(S|E|\()\d+)(?:H[DQ])?(?:[ .-]*Rip|Rp)?\b", regex.IGNORECASE), boolean, {"remove": False})
    parser.add_handler("trash", regex.compile(r"\b(?:H[DQ][ .-]*)?S[ \.\-]print\b", regex.IGNORECASE), boolean, {"remove": False})
    parser.add_handler("trash", regex.compile(r"\b(?:HD[ .-]*)?T(?:ELE)?(C|S)(?:INE|YNC)?(?:Rip)?\b", regex.IGNORECASE), boolean, {"remove": False})
    parser.add_handler("trash", regex.compile(r"\bPre.?DVD(?:Rip)?\b", regex.IGNORECASE), boolean, {"remove": False})
    parser.add_handler("trash", regex.compile(r"\b(?:DVD?|BD|BR|HD)?[ .-]*Scr(?:eener)?\b", regex.IGNORECASE), boolean, {"remove": False})
    parser.add_handler("trash", regex.compile(r"\bDVB[ .-]*(?:Rip)?\b", regex.IGNORECASE), boolean, {"remove": False})
    parser.add_handler("trash", regex.compile(r"\bSAT[ .-]*Rips?\b", regex.IGNORECASE), boolean, {"remove": False})
    parser.add_handler("trash", regex.compile(r"\bLeaked\b", regex.IGNORECASE), boolean, {"remove": True})
    parser.add_handler("trash", regex.compile(r"threesixtyp", regex.IGNORECASE), boolean, {"remove": False})
    parser.add_handler("trash", regex.compile(r"\bR5|R6\b", regex.IGNORECASE), boolean, {"remove": False})
    parser.add_handler("trash", regex.compile(r"\b(?:Deleted[ .-]*)?Scene(?:s)?\b", regex.IGNORECASE), boolean, {"remove": True})
    parser.add_handler("trash", regex.compile(r"\bHQ.?(Clean)?.?(Aud(io)?)?\b", regex.IGNORECASE), boolean, {"remove": True})

    # Date
    parser.add_handler("date", regex.compile(r"(?:\W|^)([[(]?(?:19[6-9]|20[012])[0-9]([. \-/\\])(?:0[1-9]|1[012])\2(?:0[1-9]|[12][0-9]|3[01])[])]?)(?:\W|$)"), date("YYYY MM DD"), {"remove": True})
    parser.add_handler("date", regex.compile(r"(?:\W|^)(\[?\]?(?:0[1-9]|[12][0-9]|3[01])([. \-/\\])(?:0[1-9]|1[012])\2(?:19[6-9]|20[01])[0-9][\])]?)(?:\W|$)"), date("DD MM YYYY"), {"remove": True})
    parser.add_handler("date", regex.compile(r"(?:\W)(\[?\]?(?:0[1-9]|1[012])([. \-/\\])(?:0[1-9]|[12][0-9]|3[01])\2(?:[0][1-9]|[0126789][0-9])[\])]?)(?:\W|$)"), date("MM DD YY"), {"remove": True})
    parser.add_handler("date", regex.compile(r"(?:\W)(\[?\]?(?:0[1-9]|[12][0-9]|3[01])([. \-/\\])(?:0[1-9]|1[012])\2(?:[0][1-9]|[0126789][0-9])[\])]?)(?:\W|$)"), date("DD MM YY"), {"remove": True})
    parser.add_handler(
        "date",
        regex.compile(r"(?:\W|^)([([]?(?:0?[1-9]|[12][0-9]|3[01])[. ]?(?:st|nd|rd|th)?([. \-/\\])(?:feb(?:ruary)?|jan(?:uary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sept?(?:ember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\2(?:19[7-9]|20[012])[0-9][)\]]?)(?=\W|$)", regex.IGNORECASE),
        date(["DD MMM YYYY", "Do MMM YYYY", "Do MMMM YYYY"]),
        {"remove": True},
    )
    parser.add_handler(
        "date",
        regex.compile(r"(?:\W|^)(\[?\]?(?:0?[1-9]|[12][0-9]|3[01])[. ]?(?:st|nd|rd|th)?([. \-\/\\])(?:feb(?:ruary)?|jan(?:uary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sept?(?:ember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\2(?:0[1-9]|[0126789][0-9])[\])]?)(?:\W|$)", regex.IGNORECASE),
        date("DD MMM YY"),
        {"remove": True},
    )
    parser.add_handler("date", regex.compile(r"(?:\W|^)(\[?\]?20[012][0-9](?:0[1-9]|1[012])(?:0[1-9]|[12][0-9]|3[01])[\])]?)(?:\W|$)"), date("YYYYMMDD"), {"remove": True})

    # Complete
    parser.add_handler("complete", regex.compile(r"\b((?:19\d|20[012])\d[ .]?-[ .]?(?:19\d|20[012])\d)\b"), boolean, {"remove": True})  # year range
    parser.add_handler("complete", regex.compile(r"[([][ .]?((?:19\d|20[012])\d[ .]?-[ .]?\d{2})[ .]?[)\]]"), boolean, {"remove": True})  # year range

    # Bit Rate
    parser.add_handler("bitrate", regex.compile(r"\b\d+[kmg]bps\b", regex.IGNORECASE), lowercase, {"remove": True})

    # Year
    parser.add_handler("year", regex.compile(r"\b(20[0-9]{2}|2100)(?!\D*\d{4}\b)"), integer, {"remove": True})
    parser.add_handler("year", regex.compile(r"[([]?(?!^)(?<!\d|Cap[. ]?)((?:19\d|20[012])\d)(?!\d|kbps)[)\]]?", regex.IGNORECASE), integer, {"remove": True})
    parser.add_handler("year", regex.compile(r"(?!^\w{4})^[([]?((?:19\d|20[012])\d)(?!\d|kbps)[)\]]?", regex.IGNORECASE), integer, {"remove": True})

    # Edition
    parser.add_handler("edition", regex.compile(r"\b\d{2,3}(th)?[\.\s\-\+_\/(),]Anniversary[\.\s\-\+_\/(),](Edition|Ed)?\b", regex.IGNORECASE), value("Anniversary Edition"), {"remove": True})
    parser.add_handler("edition", regex.compile(r"\bUltimate[\.\s\-\+_\/(),]Edition\b", regex.IGNORECASE), value("Ultimate Edition"), {"remove": True})
    parser.add_handler("edition", regex.compile(r"\bExtended[\.\s\-\+_\/(),]Director(\')?s\b", regex.IGNORECASE), value("Directors Cut"), {"remove": True})
    parser.add_handler("edition", regex.compile(r"\b(custom.?)?Extended\b", regex.IGNORECASE), value("Extended Edition"), {"remove": True})
    parser.add_handler("edition", regex.compile(r"\bDirector(\')?s.?Cut\b", regex.IGNORECASE), value("Directors Cut"), {"remove": True})
    parser.add_handler("edition", regex.compile(r"\bCollector(\')?s\b", regex.IGNORECASE), value("Collectors Edition"), {"remove": True})
    parser.add_handler("edition", regex.compile(r"\bTheatrical\b", regex.IGNORECASE), value("Theatrical"), {"remove": True})
    parser.add_handler("edition", regex.compile(r"\buncut(?!.gems)\b", regex.IGNORECASE), value("Uncut"), {"remove": True})
    parser.add_handler("edition", regex.compile(r"\bIMAX\b", regex.IGNORECASE), value("IMAX"), {"remove": True})
    parser.add_handler("edition", regex.compile(r"\b\.Diamond\.\b", regex.IGNORECASE), value("Diamond Edition"), {"remove": True})
    parser.add_handler("edition", regex.compile(r"\bRemaster(?:ed)?\b", regex.IGNORECASE), value("Remastered"), {"remove": True, "skipIfAlreadyFound": True})

    # Upscaled
    parser.add_handler("upscaled", regex.compile(r"\b(?:AI.?)?(Upscal(ed?|ing)|Enhanced?)\b", regex.IGNORECASE), boolean)
    parser.add_handler("upscaled", regex.compile(r"\b(?:iris2|regrade|ups(uhd|fhd|hd|4k))\b", regex.IGNORECASE), boolean)
    parser.add_handler("upscaled", regex.compile(r"\b\.AI\.\b", regex.IGNORECASE), boolean)

    # Convert
    parser.add_handler("convert", regex.compile(r"\bCONVERT\b"), boolean, {"remove": True})

    # Hardcoded
    parser.add_handler("hardcoded", regex.compile(r"\b(HC|HARDCODED)\b"), boolean, {"remove": True})

    # Proper
    parser.add_handler("proper", regex.compile(r"\b(?:REAL.)?PROPER\b", regex.IGNORECASE), boolean, {"remove": True})

    # Repack
    parser.add_handler("repack", regex.compile(r"\bREPACK|RERIP\b", regex.IGNORECASE), boolean, {"remove": True})

    # Retail
    parser.add_handler("retail", regex.compile(r"\bRetail\b", regex.IGNORECASE), boolean, {"remove": True})

    # Remastered
    parser.add_handler("remastered", regex.compile(r"\bRemaster(?:ed)?\b", regex.IGNORECASE), boolean, {"remove": True})

    # Documentary
    parser.add_handler("documentary", regex.compile(r"\bDOCU(?:menta?ry)?\b", regex.IGNORECASE), boolean, {"skipFromTitle": True})

    # Unrated
    parser.add_handler("unrated", regex.compile(r"\bunrated\b", regex.IGNORECASE), boolean, {"remove": True})

    # Uncensored
    parser.add_handler("uncensored", regex.compile(r"\buncensored\b", regex.IGNORECASE), boolean, {"remove": True})

    # Commentary
    parser.add_handler("commentary", regex.compile(r"\bcommentary\b", regex.IGNORECASE), boolean, {"remove": True})

    # Region
    parser.add_handler("region", regex.compile(r"R\dJ?\b"), uppercase, {"remove": True})
    parser.add_handler("region", regex.compile(r"\b(PAL|NTSC|SECAM)\b", regex.IGNORECASE), uppercase, {"remove": True})

    # Quality
    parser.add_handler("quality", regex.compile(r"\b(?:HD[ .-]*)?T(?:ELE)?S(?:YNC)?(?:Rip)?\b", regex.IGNORECASE), value("TeleSync"), {"remove": True})
    parser.add_handler("quality", regex.compile(r"\b(?:HD[ .-]*)?T(?:ELE)?C(?:INE)?(?:Rip)?\b"), value("TeleCine"), {"remove": True})
    parser.add_handler("quality", regex.compile(r"\b(?:DVD?|BD|BR|HD)?[ .-]*Scr(?:eener)?\b", regex.IGNORECASE), value("SCR"), {"remove": True})
    parser.add_handler("quality", regex.compile(r"\bP(?:RE)?-?(HD|DVD)(?:Rip)?\b", regex.IGNORECASE), value("SCR"), {"remove": True})
    parser.add_handler("quality", regex.compile(r"\bBlu[ .-]*Ray\b(?=.*remux)", regex.IGNORECASE), value("BluRay REMUX"), {"remove": True})
    parser.add_handler("quality", regex.compile(r"(?:BD|BR|UHD)[- ]?remux", regex.IGNORECASE), value("BluRay REMUX"), {"remove": True})
    parser.add_handler("quality", regex.compile(r"(?<=remux.*)\bBlu[ .-]*Ray\b", regex.IGNORECASE), value("BluRay REMUX"), {"remove": True})
    parser.add_handler("quality", regex.compile(r"\bremux\b", regex.IGNORECASE), value("REMUX"), {"remove": True})
    parser.add_handler("quality", regex.compile(r"\bBlu[ .-]*Ray\b(?![ .-]*Rip)", regex.IGNORECASE), value("BluRay"), {"remove": True})
    parser.add_handler("quality", regex.compile(r"\bUHD[ .-]*Rip\b", regex.IGNORECASE), value("UHDRip"), {"remove": True})
    parser.add_handler("quality", regex.compile(r"\bHD[ .-]*Rip\b", regex.IGNORECASE), value("HDRip"), {"remove": True})
    parser.add_handler("quality", regex.compile(r"\bMicro[ .-]*HD\b", regex.IGNORECASE), value("HDRip"), {"remove": True})
    parser.add_handler("quality", regex.compile(r"\b(?:BR|Blu[ .-]*Ray)[ .-]*Rip\b", regex.IGNORECASE), value("BRRip"), {"remove": True})
    parser.add_handler("quality", regex.compile(r"\bBD[ .-]*Rip\b|\bBDR\b|\bBD-RM\b|[[(]BD[\]) .,-]", regex.IGNORECASE), value("BDRip"), {"remove": True})
    parser.add_handler("quality", regex.compile(r"\b(?:HD[ .-]*)?DVD[ .-]*Rip\b", regex.IGNORECASE), value("DVDRip"), {"remove": True})
    parser.add_handler("quality", regex.compile(r"\bVHS[ .-]*Rip?\b", regex.IGNORECASE), value("VHSRip"), {"remove": True})
    parser.add_handler("quality", regex.compile(r"\bDVD(?:R\d?|.*Mux)?\b", regex.IGNORECASE), value("DVD"), {"remove": True})
    parser.add_handler("quality", regex.compile(r"\bVHS\b", regex.IGNORECASE), value("VHS"), {"remove": True})
    parser.add_handler("quality", regex.compile(r"\bPPVRip\b", regex.IGNORECASE), value("PPVRip"), {"remove": True})
    parser.add_handler("quality", regex.compile(r"\bHD.?TV.?Rip\b", regex.IGNORECASE), value("HDTVRip"), {"remove": True})
    parser.add_handler("quality", regex.compile(r"\bDVB[ .-]*(?:Rip)?\b", regex.IGNORECASE), value("HDTV"), {"remove": True})
    parser.add_handler("quality", regex.compile(r"\bSAT[ .-]*Rips?\b", regex.IGNORECASE), value("SATRip"), {"remove": True})
    parser.add_handler("quality", regex.compile(r"\bTVRips?\b", regex.IGNORECASE), value("TVRip"), {"remove": True})
    parser.add_handler("quality", regex.compile(r"\bR5\b", regex.IGNORECASE), value("R5"), {"remove": True})
    parser.add_handler("quality", regex.compile(r"\b(?:DL|WEB|BD|BR)MUX\b", regex.IGNORECASE), value("WEBMux"), {"remove": True})
    parser.add_handler("quality", regex.compile(r"\bWEB[ .-]*Rip\b", regex.IGNORECASE), value("WEBRip"), {"remove": True})
    parser.add_handler("quality", regex.compile(r"\bWEB[ .-]?DL[ .-]?Rip\b", regex.IGNORECASE), value("WEB-DLRip"), {"remove": True})
    parser.add_handler("quality", regex.compile(r"\bWEB[ .-]*(DL|.BDrip|.DLRIP)\b", regex.IGNORECASE), value("WEB-DL"), {"remove": True})
    parser.add_handler("quality", regex.compile(r"\b(?<!\w.)WEB\b|\bWEB(?!([ \.\-\(\],]+\d))\b", regex.IGNORECASE), value("WEB"), {"remove": True, "skipFromTitle": True})  #
    parser.add_handler("quality", regex.compile(r"\b(?:H[DQ][ .-]*)?CAM(?!.?(S|E|\()\d+)(?:H[DQ])?(?:[ .-]*Rip|Rp)?\b", regex.IGNORECASE), value("CAM"), {"remove": True, "skipFromTitle": True})  # can appear in a title as well, check it last
    parser.add_handler("quality", regex.compile(r"\b(?:H[DQ][ .-]*)?S[ \.\-]print", regex.IGNORECASE), value("CAM"), {"remove": True, "skipFromTitle": True})  # can appear in a title as well, check it last
    parser.add_handler("quality", regex.compile(r"\bPDTV\b", regex.IGNORECASE), value("PDTV"), {"remove": True})
    parser.add_handler("quality", regex.compile(r"\bHD(.?TV)?\b", regex.IGNORECASE), value("HDTV"), {"remove": True})

    # Video depth
    parser.add_handler("bit_depth", regex.compile(r"\bhevc\s?10\b", regex.IGNORECASE), value("10bit"))
    parser.add_handler("bit_depth", regex.compile(r"(?:8|10|12)[-\.]?(?=bit\b)", regex.IGNORECASE), value("$1bit"), {"remove": True})
    parser.add_handler("bit_depth", regex.compile(r"\bhdr10\b", regex.IGNORECASE), value("10bit"))
    parser.add_handler("bit_depth", regex.compile(r"\bhi10\b", regex.IGNORECASE), value("10bit"))

    def handle_bit_depth(context):
        result = context["result"]
        if "bit_depth" in result:
            # Replace hyphens and spaces with nothing (effectively removing them)
            result["bit_depth"] = result["bit_depth"].replace(" ", "").replace("-", "")

    parser.add_handler("bit_depth", handle_bit_depth)

    # HDR
    parser.add_handler("hdr", regex.compile(r"\bDV\b|dolby.?vision|\bDoVi\b", regex.IGNORECASE), uniq_concat(value("DV")), {"remove": True, "skipIfAlreadyFound": False})
    parser.add_handler("hdr", regex.compile(r"HDR10(?:\+|[-\.\s]?plus)", regex.IGNORECASE), uniq_concat(value("HDR10+")), {"remove": True, "skipIfAlreadyFound": False})
    parser.add_handler("hdr", regex.compile(r"\bHDR(?:10)?\b", regex.IGNORECASE), uniq_concat(value("HDR")), {"remove": True, "skipIfAlreadyFound": False})
    parser.add_handler("hdr", regex.compile(r"\bSDR\b", regex.IGNORECASE), uniq_concat(value("SDR")), {"remove": True, "skipIfAlreadyFound": False})

    # Codec
    parser.add_handler("codec", regex.compile(r"\b[hx][\. \-]?264\b", regex.IGNORECASE), value("avc"), {"remove": True})
    parser.add_handler("codec", regex.compile(r"\b[hx][\. \-]?265\b", regex.IGNORECASE), value("hevc"), {"remove": True})
    parser.add_handler("codec", regex.compile(r"\bHEVC10(bit)?\b|\b[xh][\. \-]?265\b", regex.IGNORECASE), value("hevc"), {"remove": True})
    parser.add_handler("codec", regex.compile(r"\bhevc(?:\s?10)?\b", regex.IGNORECASE), value("hevc"), {"remove": True, "skipIfAlreadyFound": False})
    parser.add_handler("codec", regex.compile(r"\bdivx|xvid\b", regex.IGNORECASE), value("xvid"), {"remove": True, "skipIfAlreadyFound": False})
    parser.add_handler("codec", regex.compile(r"\bavc\b", regex.IGNORECASE), value("avc"), {"remove": True, "skipIfAlreadyFound": False})
    parser.add_handler("codec", regex.compile(r"\bav1\b", regex.IGNORECASE), value("av1"), {"remove": True, "skipIfAlreadyFound": False})
    parser.add_handler("codec", regex.compile(r"\b(?:mpe?g\d*)\b", regex.IGNORECASE), value("mpeg"), {"remove": True, "skipIfAlreadyFound": False})

    def handle_space_in_codec(context):
        if context["result"].get("codec"):
            context["result"]["codec"] = regex.sub("[ .-]", "", context["result"]["codec"])

    parser.add_handler("codec", handle_space_in_codec)

    # Channels
    parser.add_handler("channels", regex.compile(r"5[\.\s]1(?:ch|-S\d+)?\b", regex.IGNORECASE), uniq_concat(value("5.1")), {"remove": True, "skipIfAlreadyFound": False})
    parser.add_handler("channels", regex.compile(r"\b(?:x[2-4]|5[\W]1(?:x[2-4])?)\b", regex.IGNORECASE), uniq_concat(value("5.1")), {"remove": True, "skipIfAlreadyFound": False})
    parser.add_handler("channels", regex.compile(r"7[\.\s]1(?:ch|-S\d+)?\b", regex.IGNORECASE), uniq_concat(value("7.1")), {"remove": True, "skipIfAlreadyFound": False})
    parser.add_handler("channels", regex.compile(r"\b7[\.\- ]1(.?ch(annel)?)?\b", regex.IGNORECASE), uniq_concat(value("7.1")), {"remove": True, "skipIfAlreadyFound": False})
    parser.add_handler("channels", regex.compile(r"\b(?:x[2-4]|7[\W]1(?:x[2-4])?)\b", regex.IGNORECASE), uniq_concat(value("7.1")), {"remove": True, "skipIfAlreadyFound": False})
    parser.add_handler("channels", regex.compile(r"\+?2[\.\s]0(?:x[2-4])?\b", regex.IGNORECASE), uniq_concat(value("2.0")), {"remove": True, "skipIfAlreadyFound": False})
    parser.add_handler("channels", regex.compile(r"\b2\.0\b", regex.IGNORECASE), uniq_concat(value("2.0")), {"remove": True, "skipIfAlreadyFound": False})
    parser.add_handler("channels", regex.compile(r"\bstereo\b", regex.IGNORECASE), uniq_concat(value("stereo")), {"remove": False, "skipIfAlreadyFound": False})
    parser.add_handler("channels", regex.compile(r"\bmono\b", regex.IGNORECASE), uniq_concat(value("mono")), {"remove": False, "skipIfAlreadyFound": False})

    # Audio
    parser.add_handler("audio", regex.compile(r"\b(?!.+HR)(DTS.?HD.?Ma(ster)?|DTS.?X)\b", regex.IGNORECASE), uniq_concat(value("DTS Lossless")), {"remove": True, "skipIfAlreadyFound": False})
    parser.add_handler("audio", regex.compile(r"\bDTS(?!(.?HD.?Ma(ster)?|.X)).?(HD.?HR|HD)?\b", regex.IGNORECASE), uniq_concat(value("DTS Lossy")), {"remove": True, "skipIfAlreadyFound": False})
    parser.add_handler("audio", regex.compile(r"\b(Dolby.?)?Atmos\b", regex.IGNORECASE), uniq_concat(value("Atmos")), {"remove": True, "skipIfAlreadyFound": False})
    parser.add_handler("audio", regex.compile(r"\b(True[ .-]?HD|\.True\.)\b", regex.IGNORECASE), uniq_concat(value("TrueHD")), {"remove": True, "skipIfAlreadyFound": False, "skipFromTitle": True})
    parser.add_handler("audio", regex.compile(r"\bTRUE\b"), uniq_concat(value("TrueHD")), {"remove": True, "skipIfAlreadyFound": False, "skipFromTitle": True})
    parser.add_handler("audio", regex.compile(r"\bFLAC(?:\d\.\d)?(?:x\d+)?\b", regex.IGNORECASE), uniq_concat(value("FLAC")), {"remove": True, "skipIfAlreadyFound": False})
    parser.add_handler("audio", regex.compile(r"DD2?[\+p]|DD Plus|Dolby Digital Plus|DDP5[ \.\_]1|E-?AC-?3(?:-S\d+)?", regex.IGNORECASE), uniq_concat(value("Dolby Digital Plus")), {"remove": True, "skipIfAlreadyFound": False})
    parser.add_handler("audio", regex.compile(r"\b(DD|Dolby.?Digital|DolbyD|AC-?3(x2)?(?:-S\d+)?)\b", regex.IGNORECASE), uniq_concat(value("Dolby Digital")), {"remove": True, "skipIfAlreadyFound": False})
    parser.add_handler("audio", regex.compile(r"\bQ?Q?AAC(x?2)?\b", regex.IGNORECASE), uniq_concat(value("AAC")), {"remove": True, "skipIfAlreadyFound": False})
    parser.add_handler("audio", regex.compile(r"\bL?PCM\b", regex.IGNORECASE), uniq_concat(value("PCM")), {"remove": True, "skipIfAlreadyFound": False})
    parser.add_handler("audio", regex.compile(r"\bOPUS(\b|\d)(?!.*[ ._-](\d{3,4}p))"), uniq_concat(value("OPUS")), {"remove": True, "skipIfAlreadyFound": False})
    parser.add_handler("audio", regex.compile(r"\b(H[DQ])?.?(Clean.?Aud(io)?)\b", regex.IGNORECASE), uniq_concat(value("HQ Clean Audio")), {"remove": True, "skipIfAlreadyFound": False})

    # Group
    parser.add_handler("group", regex.compile(r"- ?(?!\d+$|S\d+|\d+x|ep?\d+|[^[]+]$)([^\-. []+[^\-. [)\]\d][^\-. [)\]]*)(?:\[[\w.-]+])?(?=\.\w{2,4}$|$)", regex.IGNORECASE), none, {"remove": False})

    # Volume
    parser.add_handler("volumes", regex.compile(r"\bvol(?:s|umes?)?[. -]*(?:\d{1,2}[., +/\\&-]+)+\d{1,2}\b", regex.IGNORECASE), range_func, {"remove": True})

    def handle_volumes(context):
        title = context["title"]
        result = context["result"]
        matched = context["matched"]

        start_index = matched.get("year", {}).get("match_index", 0)
        match = regex.search(r"\bvol(?:ume)?[. -]*(\d{1,2})", title[start_index:], regex.IGNORECASE)

        if match:
            matched["volumes"] = {"match": match.group(0), "match_index": match.start()}
            result["volumes"] = [int(match.group(1))]
            return {"raw_match": match.group(0), "match_index": match.start() + start_index, "remove": True}
        return None

    parser.add_handler("volumes", handle_volumes)

    # Pre-Language
    parser.add_handler("languages", regex.compile(r"\b(temporadas?|completa)\b", regex.IGNORECASE), uniq_concat(value("es")), {"skipIfAlreadyFound": False})

    # Complete
    parser.add_handler("complete", regex.compile(r"\b(?:INTEGRALE?|INTÉGRALE?)\b", regex.IGNORECASE), boolean, {"remove": True, "skipIfAlreadyFound": False})
    parser.add_handler("complete", regex.compile(r"(Movie|Complete).Collection"), boolean, {"remove": True, "skipIfAlreadyFound": False})
    parser.add_handler("complete", regex.compile(r"Complete(.\d{1,2})"), boolean, {"remove": True, "skipIfAlreadyFound": False})
    parser.add_handler("complete", regex.compile(r"(?:\bthe\W)?(?:\bcomplete|collection|dvd)?\b[ .]?\bbox[ .-]?set\b", regex.IGNORECASE), boolean, {"remove": True})
    parser.add_handler("complete", regex.compile(r"(?:\bthe\W)?(?:\bcomplete|collection|dvd)?\b[ .]?\bmini[ .-]?series\b", regex.IGNORECASE), boolean)
    parser.add_handler("complete", regex.compile(r"(?:\bthe\W)?(?:\bcomplete|full|all)\b.*\b(?:series|seasons|collection|episodes|set|pack|movies)\b", regex.IGNORECASE), boolean)
    parser.add_handler("complete", regex.compile(r"\b(?:series|movies?)\b.*\b(?:complete|collection)\b", regex.IGNORECASE), boolean, {"remove": True})
    parser.add_handler("complete", regex.compile(r"(?:\bthe\W)?\bultimate\b[ .]\bcollection\b", regex.IGNORECASE), boolean, {"skipIfAlreadyFound": False})
    parser.add_handler("complete", regex.compile(r"\bcollection\b.*\b(?:set|pack|movies)\b", regex.IGNORECASE), boolean)
    parser.add_handler("complete", regex.compile(r"\bcollection(?:(\s\[|\s\())", regex.IGNORECASE), boolean, {"remove": True})
    parser.add_handler("complete", regex.compile(r"duology|trilogy|quadr[oi]logy|tetralogy|pentalogy|hexalogy|heptalogy|anthology", regex.IGNORECASE), boolean, {"skipIfAlreadyFound": False})
    parser.add_handler("complete", regex.compile(r"\bcompleta\b", regex.IGNORECASE), boolean, {"remove": True})
    parser.add_handler("complete", regex.compile(r"\bsaga\b", regex.IGNORECASE), boolean, {"skipFromTitle": True, "skipIfAlreadyFound": True})
    parser.add_handler("complete", regex.compile(r"\b\[Complete\]\b", regex.IGNORECASE), boolean, {"remove": True})
    parser.add_handler("complete", regex.compile(r"(?<!A.?|The.?)\bComplete\b", regex.IGNORECASE), boolean, {"remove": True})
    parser.add_handler("complete", regex.compile(r"COMPLETE"), boolean, {"remove": True})

    # === POCZĄTEK SEKCJI Z POLSKIMI REGUŁAMI DLA "COMPLETE" ===

    # Słowa kluczowe inicjujące polską nazwę kolekcji
    # Możesz rozszerzyć tę listę o inne synonimy
    polish_collection_prefixes = r"(?:Kolekcja|Zbiór|Zbior|Antologia|Pakiet|Cykl)"

    # Słowa określające typ kolekcji (najczęstsze formy,
    # głównie mianownik l.poj/mn i dopełniacz l.mn).
    # Możesz rozszerzyć tę listę o inne typy lub formy gramatyczne.
    polish_collection_nouns = (
        r"(?:film(?:ów|ow)?|serial(?:i|ów|ow)?|odcink(?:i|ów|ow)?"
        r"|części|sezon(?:y|ów|ow)?"
        r"|komiks(?:y|ów|ow)?"
        r"|bajek|bajki" # bajek (D.lm), bajki (M.lm)
        r"|trylogi(?:a|i)" # trylogia (M.lp), trylogii (D.lp)
        r"|sag(?:a|i)"     # saga (M.lp), sagi (D.lp)
        r"|wydani(?:e|a|ń|n))" # wydanie (M.lp), wydania (M.lm), wydań (D.lm)
    )

    # Handler dla fraz typu "Kolekcja filmów Batman..." oraz "Kolekcja Batman..." na początku tytułu.
    # Usuwa całą frazę np. "Kolekcja filmów" lub samo "Kolekcja".
    parser.add_handler(
        "complete",
        regex.compile(
            # ^\s*                     - początek stringa, opcjonalne spacje
            # (?:{prefixes})           - dopasuj jedno ze słów kluczowych (np. "Kolekcja") (grupa nieprzechwytująca)
            # (?:                      - początek opcjonalnej grupy dla typu kolekcji (grupa nieprzechwytująca)
            #   \s+                   - wymagana spacja oddzielająca
            #   (?:{nouns})\b         - dopasuj jedno ze słów określających typ (np. "filmów") z granicą słowa
            # )?                       - cała grupa typu kolekcji jest opcjonalna
            # \b                       - granica słowa na końcu całej dopasowanej frazy
            #                           (np. po "Kolekcja" lub po "Kolekcja filmów")
            rf"^\s*(?:{polish_collection_prefixes})(?:\s+(?:{polish_collection_nouns})\b)?\b",
            regex.IGNORECASE
        ),
        boolean,  # Transformer ustawia wartość na True
        {"remove": True, "skipIfAlreadyFound": False}
    )

    # Specjalna polska fraza oznaczająca kolekcję filmową: "Filmy Świąteczne"
    # (uwzględnia też wariant bez ogonków: "Filmy Swiateczne")
    parser.add_handler(
        "complete",
        regex.compile(r"\bFilmy[\s._-]+(?:Świąteczne|Swiateczne)\b", regex.IGNORECASE),
        boolean,
        {"remove": True, "skipIfAlreadyFound": False}
    )

    # Istniejące, bardziej ogólne polskie reguły dla "complete" (np. samo "KOMPLETNY")
    # powinny być tutaj lub później.
    # Poniżej przykłady z Twojego oryginalnego kodu, które zostają:

    # Oryginał: r"\b(?:INTEGRALE?|INTÉGRALE?)\b" (francuski)
    # Polskie odpowiedniki dla "kompletny", "całość"
    parser.add_handler("complete", regex.compile(r"\b(?:KOMPLETNY|KOMPLETNA|KOMPLETNE|CAŁY|CAŁA|CAŁE|CAŁOŚĆ|KOMPLET)\b", regex.IGNORECASE), boolean, {"remove": True, "skipIfAlreadyFound": False})
    parser.add_handler("complete", regex.compile(r"\b(?:KOMPLETNY|KOMPLETNA|KOMPLETNE|CALY|CALA|CALE|CALOSC|KOMPLET)\b", regex.IGNORECASE), boolean, {"remove": True, "skipIfAlreadyFound": False})

    # Oryginał: r"(?:\bthe\W)?(?:\bcomplete|full|all)\b.*\b(?:series|seasons|collection|episodes|set|pack|movies)\b"
    # Polskie odpowiedniki dla "kompletna seria", "wszystkie sezony", "pełna kolekcja", "całe odcinki" itp.
    # Te reguły są bardziej złożone i szukają kombinacji słów, więc nowa reguła powyżej ich nie zastępuje.
    parser.add_handler("complete", regex.compile(r"\b(?:komplet(?:ny|na|ne|u)|pełn(?:y|a|e|ej)|cał(?:y|a|e|ości)|wszystkie)\b.*\b(?:seri(?:a|i|e|ał)|sezon(?:y|ów)|kolekc(?:ja|ji)|odcink(?:i|ów)|film(?:y|ów)|części|cz??ści|zestaw|pakiet)\b", regex.IGNORECASE), boolean, {"remove": True})
    parser.add_handler("complete", regex.compile(r"\b(?:komplet(?:ny|na|ne|u)|peln(?:y|a|e|ej)|cal(?:y|a|e|osci)|wszystkie)\b.*\b(?:seri(?:a|i|e|al)|sezon(?:y|ow)|kolekc(?:ja|ji)|odcink(?:i|ow)|film(?:y|ow)|czesci|zestaw|pakiet)\b", regex.IGNORECASE), boolean, {"remove": True})

    # Oryginał: r"\b(?:series|movies?)\b.*\b(?:complete|collection)\b"
    # Polskie odpowiedniki dla "seria kompletna", "filmy kolekcja" itp.
    parser.add_handler("complete", regex.compile(r"\b(?:seri(?:a|i|e|ał)|film(?:y|ów)?|sezon(?:y|ów)?|odcink(?:i|ów)?)\b.*\b(?:komplet(?:ny|na|ne|u)|cał(?:y|a|e|ości)|kolekc(?:ja|ji))\b", regex.IGNORECASE), boolean, {"remove": True})
    parser.add_handler("complete", regex.compile(r"\b(?:seri(?:a|i|e|al)|film(?:y|ow)?|sezon(?:y|ow)?|odcink(?:i|ow)?)\b.*\b(?:komplet(?:ny|na|ne|u)|cal(?:y|a|e|osci)|kolekc(?:ja|ji))\b", regex.IGNORECASE), boolean, {"remove": True})

    # Oryginał: r"duology|trilogy|quadr[oi]logy|tetralogy|pentalogy|hexalogy|heptalogy|anthology"
    # Polski odpowiednik dla "anthology" to "antologia"
    parser.add_handler("complete", regex.compile(r"\bantologi[ai]\b", regex.IGNORECASE), boolean, {"skipIfAlreadyFound": False}) # antologia, antologii

    # === KONIEC SEKCJI Z POLSKIMI REGUŁAMI DLA "COMPLETE" ===

    # Seasons
    parser.add_handler("seasons", regex.compile(r"(?:complete\W|seasons?\W|\W|^)((?:s\d{1,2}[., +/\\&-]+)+s\d{1,2}\b)", regex.IGNORECASE), concat_values(range_func), {"remove": True})
    parser.add_handler("seasons", regex.compile(r"(?:complete\W|seasons?\W|\W|^)[([]?(s\d{2,}-\d{2,}\b)[)\]]?", regex.IGNORECASE), concat_values(range_func), {"remove": True})
    parser.add_handler("seasons", regex.compile(r"(?:complete\W|seasons?\W|\W|^)[([]?(s[1-9]-[2-9])[)\]]?", regex.IGNORECASE), concat_values(range_func), {"remove": True})
    parser.add_handler("seasons", regex.compile(r"\d+ª(?:.+)?(?:a.?)?\d+ª(?:(?:.+)?(?:temporadas?))", regex.IGNORECASE), concat_values(range_func), {"remove": True})
    parser.add_handler("seasons", regex.compile(r"(?:(?:\bthe\W)?\bcomplete\W)?(?:seasons?|[Сс]езони?|temporadas?)[. ]?[-:]?[. ]?[([]?((?:\d{1,2}[., /\\&]+)+\d{1,2}\b)[)\]]?", regex.IGNORECASE), concat_values(range_func), {"remove": True})
    parser.add_handler("seasons", regex.compile(r"(?:(?:\bthe\W)?\bcomplete\W)?(?:seasons?|[Сс]езони?|temporadas?)[. ]?[-:]?[. ]?[([]?((?:\d{1,2}[.-]+)+[1-9]\d?\b)[)\]]?", regex.IGNORECASE), concat_values(range_func), {"remove": True})
    parser.add_handler("seasons", regex.compile(r"(?:(?:\bthe\W)?\bcomplete\W)?season[. ]?[([]?((?:\d{1,2}[. -]+)+[1-9]\d?\b)[)\]]?(?!.*\.\w{2,4}$)", regex.IGNORECASE), concat_values(range_func), {"remove": True})
    parser.add_handler("seasons", regex.compile(r"(?:(?:\bthe\W)?\bcomplete\W)?\bseasons?\b[. -]?(\d{1,2}[. -]?(?:to|thru|and|\+|:)[. -]?\d{1,2})\b", regex.IGNORECASE), concat_values(range_func), {"remove": True})
    parser.add_handler("seasons", regex.compile(r"(?:(?:\bthe\W)?\bcomplete\W)?(?:saison|seizoen|season|series|temp(?:orada)?):?[. ]?(\d{1,2})\b", regex.IGNORECASE), concat_values(integer))
    parser.add_handler("seasons", regex.compile(r"(\d{1,2})(?:-?й)?[. _]?(?:[Сс]езон|sez(?:on)?)(?:\W?\D|$)", regex.IGNORECASE), concat_values(integer), {"remove": True})
    parser.add_handler("seasons", regex.compile(r"[Сс]езон:?[. _]?№?(\d{1,2})(?!\d)", regex.IGNORECASE), concat_values(integer), {"remove": True})
    parser.add_handler("seasons", regex.compile(r"(?:\D|^)(\d{1,2})Â?[°ºªa]?[. ]*temporada", regex.IGNORECASE), concat_values(integer), {"remove": True})
    parser.add_handler("seasons", regex.compile(r"t(\d{1,3})(?:[ex]+|$)", regex.IGNORECASE), concat_values(integer), {"remove": True})
    parser.add_handler("seasons", regex.compile(r"(?:(?:\bthe\W)?\bcomplete)?(?<![a-z])\bs(\d{1,3})(?:[\Wex]|\d{2}\b|$)", regex.IGNORECASE), concat_values(integer), {"remove": False, "skipIfAlreadyFound": False})
    parser.add_handler("seasons", regex.compile(r"(?:(?:\bthe\W)?\bcomplete\W)?(?:\W|^)(\d{1,2})[. ]?(?:st|nd|rd|th)[. ]*season", regex.IGNORECASE), concat_values(integer))
    parser.add_handler("seasons", regex.compile(r"(?<=S)\d{2}(?=E\d+)"), concat_values(integer), {"remove": True})
    parser.add_handler("seasons", regex.compile(r"(?:\D|^)(\d{1,2})[xх]\d{1,3}(?:\D|$)"), concat_values(integer))
    parser.add_handler("seasons", regex.compile(r"\bSn([1-9])(?:\D|$)"), concat_values(integer))
    parser.add_handler("seasons", regex.compile(r"[[(](\d{1,2})\.\d{1,3}[)\]]"), concat_values(integer))
    parser.add_handler("seasons", regex.compile(r"-\s?(\d{1,2})\.\d{2,3}\s?-"), concat_values(integer))
    parser.add_handler("seasons", regex.compile(r"(?:^|\/)(\d{1,2})-\d{2}\b(?!-\d)"), concat_values(integer))
    parser.add_handler("seasons", regex.compile(r"[^\w-](\d{1,2})-\d{2}(?=\.\w{2,4}$)"), concat_values(integer))
    parser.add_handler("seasons", regex.compile(r"(?<!\bEp?(?:isode)? ?\d+\b.*)\b(\d{2})[ ._]\d{2}(?:.F)?\.\w{2,4}$"), concat_values(integer))
    parser.add_handler("seasons", regex.compile(r"\bEp(?:isode)?\W+(\d{1,2})\.\d{1,3}\b", regex.IGNORECASE), concat_values(integer))
    parser.add_handler("seasons", regex.compile(r"\bSeasons?\b.*\b(\d{1,2}-\d{1,2})\b", regex.IGNORECASE), concat_values(range_func), {"remove": True})
    parser.add_handler("seasons", regex.compile(r"(?:\W|^)(\d{1,2})(?:e|ep)\d{1,3}(?:\W|$)", regex.IGNORECASE), concat_values(integer))
    
    # Seasons
    # Oryginał: r"\d+ª(?:.+)?(?:a.?)?\d+ª(?:(?:.+)?(?:temporadas?))" (hiszpański/portugalski 'temporada')
    # Polski odpowiednik: "sezon"
    parser.add_handler("seasons", regex.compile(r"\d+(?:.+)?(?:do|-)\d+(?:(?:.+)?(?:sezon(?:y|ów|ami)?))", regex.IGNORECASE), concat_values(range_func), {"remove": True})
    parser.add_handler("seasons", regex.compile(r"\d+(?:.+)?(?:do|-)\d+(?:(?:.+)?(?:sezon(?:y|ow|ami)?))", regex.IGNORECASE), concat_values(range_func), {"remove": True})

    # Oryginał: r"(?:(?:\bthe\W)?\bcomplete\W)?(?:seasons?|[Сс]езони?|temporadas?)[. ]?[-:]?[. ]?[([]?((?:\d{1,2}[., /\\&]+)+\d{1,2}\b)[)\]]?" (rosyjski/hiszpański/portugalski)
    # Polski odpowiednik: "sezony"
    parser.add_handler("seasons", regex.compile(r"(?:(?:\bcały\W)?\bkomplet(?:ny|na|ne)\W)?(?:sezon(?:y|u|ów)?)[. ]?[-:]?[. ]?[([]?((?:\d{1,2}[., /\\&]+)+\d{1,2}\b)[)\]]?", regex.IGNORECASE), concat_values(range_func), {"remove": True})
    parser.add_handler("seasons", regex.compile(r"(?:(?:\bcaly\W)?\bkomplet(?:ny|na|ne)\W)?(?:sezon(?:y|u|ow)?)[. ]?[-:]?[. ]?[([]?((?:\d{1,2}[., /\\&]+)+\d{1,2}\b)[)\]]?", regex.IGNORECASE), concat_values(range_func), {"remove": True})

    # Oryginał: r"(?:(?:\bthe\W)?\bcomplete\W)?(?:seasons?|[Сс]езони?|temporadas?)[. ]?[-:]?[. ]?[([]?((?:\d{1,2}[.-]+)+[1-9]\d?\b)[)\]]?" (rosyjski/hiszpański/portugalski)
    parser.add_handler("seasons", regex.compile(r"(?:(?:\bcały\W)?\bkomplet(?:ny|na|ne)\W)?(?:sezon(?:y|u|ów)?)[. ]?[-:]?[. ]?[([]?((?:\d{1,2}[.-]+)+[1-9]\d?\b)[)\]]?", regex.IGNORECASE), concat_values(range_func), {"remove": True})
    parser.add_handler("seasons", regex.compile(r"(?:(?:\bcaly\W)?\bkomplet(?:ny|na|ne)\W)?(?:sezon(?:y|u|ow)?)[. ]?[-:]?[. ]?[([]?((?:\d{1,2}[.-]+)+[1-9]\d?\b)[)\]]?", regex.IGNORECASE), concat_values(range_func), {"remove": True})

    # Oryginał: r"(?:(?:\bthe\W)?\bcomplete\W)?season[. ]?[([]?((?:\d{1,2}[. -]+)+[1-9]\d?\b)[)\]]?(?!.*\.\w{2,4}$)"
    parser.add_handler("seasons", regex.compile(r"(?:(?:\bcały\W)?\bkomplet(?:ny|na|ne)\W)?sezon[. ]?[([]?((?:\d{1,2}[. -]+)+[1-9]\d?\b)[)\]]?(?!.*\.\w{2,4}$)", regex.IGNORECASE), concat_values(range_func), {"remove": True})
    parser.add_handler("seasons", regex.compile(r"(?:(?:\bcaly\W)?\bkomplet(?:ny|na|ne)\W)?sezon[. ]?[([]?((?:\d{1,2}[. -]+)+[1-9]\d?\b)[)\]]?(?!.*\.\w{2,4}$)", regex.IGNORECASE), concat_values(range_func), {"remove": True})

    # Oryginał: r"(?:(?:\bthe\W)?\bcomplete\W)?\bseasons?\b[. -]?(\d{1,2}[. -]?(?:to|thru|and|\+|:)[. -]?\d{1,2})\b"
    # Polskie "do", "i", "oraz" zamiast "to", "thru", "and"
    parser.add_handler("seasons", regex.compile(r"(?:(?:\bcały\W)?\bkomplet(?:ny|na|ne)\W)?\bsezon(?:y|u|ów)?\b[. -]?(\d{1,2}[. -]?(?:do|i|oraz|\+|:)[. -]?\d{1,2})\b", regex.IGNORECASE), concat_values(range_func), {"remove": True})
    parser.add_handler("seasons", regex.compile(r"(?:(?:\bcaly\W)?\bkomplet(?:ny|na|ne)\W)?\bsezon(?:y|u|ow)?\b[. -]?(\d{1,2}[. -]?(?:do|i|oraz|\+|:)[. -]?\d{1,2})\b", regex.IGNORECASE), concat_values(range_func), {"remove": True})

    # Oryginał: r"(?:(?:\bthe\W)?\bcomplete\W)?(?:saison|seizoen|season|series|temp(?:orada)?):?[. ]?(\d{1,2})\b" (francuski/holenderski/hiszpański/portugalski)
    # Polski odpowiednik: "sezon", "seria"
    parser.add_handler("seasons", regex.compile(r"(?:(?:\bcały\W)?\bkomplet(?:ny|na|ne)\W)?(?:sezon|seria|ser(?:i|ii)):?[. ]?(\d{1,2})\b", regex.IGNORECASE), concat_values(integer))
    parser.add_handler("seasons", regex.compile(r"(?:(?:\bcaly\W)?\bkomplet(?:ny|na|ne)\W)?(?:sezon|seria|ser(?:i|ii)):?[. ]?(\d{1,2})\b", regex.IGNORECASE), concat_values(integer))

    # Oryginał: r"(\d{1,2})(?:-?й)?[. _]?(?:[Сс]езон|sez(?:on)?)(?:\W?\D|$)" (rosyjski)
    # Polski odpowiednik, np. "1-szy sezon", "2-gi sezon"
    parser.add_handler("seasons", regex.compile(r"(\d{1,2})(?:-?[sS][zZ][yY]|[gG][iI]|[cC][iI]|[tT][yY])?[. _]?(?:sezon)(?:\W?\D|$)", regex.IGNORECASE), concat_values(integer), {"remove": True}) # np. 1-szy, 2-gi, 3-ci, 4-ty
    parser.add_handler("seasons", regex.compile(r"(\d{1,2})(?:-?[sS][zZ][yY]|[gG][iI]|[cC][iI]|[tT][yY])?[. _]?(?:sezon)(?:\W?\D|$)", regex.IGNORECASE), concat_values(integer), {"remove": True})

    # Oryginał: r"[Сс]езон:?[. _]?№?(\d{1,2})(?!\d)" (rosyjski)
    # Polski odpowiednik: "Sezon nr X"
    parser.add_handler("seasons", regex.compile(r"Sezon:?[. _]?Nr\.?:?[. _]?(\d{1,2})(?!\d)", regex.IGNORECASE), concat_values(integer), {"remove": True})

    # Oryginał: r"(?:\D|^)(\d{1,2})Â?[°ºªa]?[. ]*temporada" (hiszpański/portugalski)
    # Polski odpowiednik: "1-szy sezon"
    parser.add_handler("seasons", regex.compile(r"(?:\D|^)(\d{1,2})(?:-?[sS][zZ][yY]|[gG][aA]|[cC][iI]|[tT][aA])?[. ]*sezon", regex.IGNORECASE), concat_values(integer), {"remove": True}) # np. 1-szy, 2-ga, 3-ci, 4-ta
    parser.add_handler("seasons", regex.compile(r"(?:\D|^)(\d{1,2})(?:-?[sS][zZ][yY]|[gG][aA]|[cC][iI]|[tT][aA])?[. ]*sezon", regex.IGNORECASE), concat_values(integer), {"remove": True})

    # Oryginał: r"(?:(?:\bthe\W)?\bcomplete\W)?(?:\W|^)(\d{1,2})[. ]?(?:st|nd|rd|th)[. ]*season"
    # Polskie końcówki liczebników porządkowych
    parser.add_handler("seasons", regex.compile(r"(?:(?:\bcały\W)?\bkomplet(?:ny|na|ne)\W)?(?:\W|^)(\d{1,2})[. ]?(?:-?(?:szy|gi|ci|ty|my|wy))?[. ]*sezon", regex.IGNORECASE), concat_values(integer))
    parser.add_handler("seasons", regex.compile(r"(?:(?:\bcaly\W)?\bkomplet(?:ny|na|ne)\W)?(?:\W|^)(\d{1,2})[. ]?(?:-?(?:szy|gi|ci|ty|my|wy))?[. ]*sezon", regex.IGNORECASE), concat_values(integer))

    # 1) SxxEyy lub SxxOyy lub SxxODCyy → wyciągnij „xx” jako numer sezonu
    parser.add_handler(
        "seasons",
        # po literze S bierzemy dwie cyfry, jeśli dalej występuje E lub O
        regex.compile(r"(?<=\bS)(\d{2})(?=[EO])", regex.IGNORECASE),
        array(integer)
    )
    parser.add_handler(
        "seasons",
        # po literze S bierzemy dwie cyfry, jeśli dalej występuje O (np. S01O01)
        regex.compile(r"(?<=\bS)(\d{2})(?=[Oo])", regex.IGNORECASE),
        array(integer)
    )
    parser.add_handler(
        "seasons",
        # po literze S bierzemy dwie cyfry, jeśli dalej występuje ODC (np. S01ODC01)
        regex.compile(r"(?<=\bS)(\d{2})(?=[Oo][dD][cC])", regex.IGNORECASE),
        array(integer)
    )

    # Episodes
    parser.add_handler("episodes", regex.compile(r"(?:[\W\d]|^)e[ .]?[([]?(\d{1,3}(?:[ .-]*(?:[&+]|e){1,2}[ .]?\d{1,3})+)(?:\W|$)", regex.IGNORECASE), range_func)
    parser.add_handler("episodes", regex.compile(r"(?:[\W\d]|^)ep[ .]?[([]?(\d{1,3}(?:[ .-]*(?:[&+]|ep){1,2}[ .]?\d{1,3})+)(?:\W|$)", regex.IGNORECASE), range_func)
    parser.add_handler("episodes", regex.compile(r"(?:[\W\d]|^)\d+[xх][ .]?[([]?(\d{1,3}(?:[ .]?[xх][ .]?\d{1,3})+)(?:\W|$)", regex.IGNORECASE), range_func)
    parser.add_handler("episodes", regex.compile(r"(?:[\W\d]|^)(?:episodes?|[Сс]ерии:?)[ .]?[([]?(\d{1,3}(?:[ .+]*[&+][ .]?\d{1,3})+)(?:\W|$)", regex.IGNORECASE), range_func)
    parser.add_handler("episodes", regex.compile(r"[([]?(?:\D|^)(\d{1,3}[ .]?ao[ .]?\d{1,3})[)\]]?(?:\W|$)", regex.IGNORECASE), range_func)
    parser.add_handler("episodes", regex.compile(r"(?:[\W\d]|^)(?:e|eps?|episodes?|[Сс]ерии:?|\d+[xх])[ .]*[([]?(\d{1,3}(?:-\d{1,3})+)(?:\W|$)", regex.IGNORECASE), range_func)
    parser.add_handler("episodes", regex.compile(r"[st]\d{1,2}[. ]?[xх-]?[. ]?(?:e|x|х|ep|-|\.)[. ]?(\d{1,4})(?:[abc]|v0?[1-4]|\D|$)", regex.IGNORECASE), array(integer), {"remove": True})
    parser.add_handler("episodes", regex.compile(r"\b[st]\d{2}(\d{2})\b", regex.IGNORECASE), array(integer))
    parser.add_handler("episodes", regex.compile(r"(?:\W|^)(\d{1,3}(?:[ .]*~[ .]*\d{1,3})+)(?:\W|$)", regex.IGNORECASE), range_func)
    parser.add_handler("episodes", regex.compile(r"-\s(\d{1,3}[ .]*-[ .]*\d{1,3})(?!-\d)(?:\W|$)", regex.IGNORECASE), range_func)
    parser.add_handler("episodes", regex.compile(r"s\d{1,2}\s?\((\d{1,3}[ .]*-[ .]*\d{1,3})\)", regex.IGNORECASE), range_func)
    parser.add_handler("episodes", regex.compile(r"(?:^|\/)\d{1,2}-(\d{2})\b(?!-\d)"), array(integer))
    parser.add_handler("episodes", regex.compile(r"(?<!\d-)\b\d{1,2}-(\d{2})(?=\.\w{2,4}$)"), array(integer))
    parser.add_handler("episodes", regex.compile(r"(?<=^\[.+].+)[. ]+-[. ]+(\d{1,4})[. ]+(?=\W)", regex.IGNORECASE), array(integer), {"remove": True})
    parser.add_handler("episodes", regex.compile(r"(?<!(?:seasons?|[Сс]езони?)\W*)(?:[ .([-]|^)(\d{1,3}(?:[ .]?[,&+~][ .]?\d{1,3})+)(?:[ .)\]-]|$)", regex.IGNORECASE), range_func)
    parser.add_handler("episodes", regex.compile(r"(?<!(?:seasons?|[Сс]езони?)\W*)(?:[ .([-]|^)(\d{1,3}(?:-\d{1,3})+)(?:[ .)(\]]|-\D|$)", regex.IGNORECASE), range_func)
    parser.add_handler("episodes", regex.compile(r"\bEp(?:isode)?\W+\d{1,2}\.(\d{1,3})\b", regex.IGNORECASE), array(integer))
    parser.add_handler("episodes", regex.compile(r"Ep.\d+.-.\d+", regex.IGNORECASE), range_func, {"remove": True})
    parser.add_handler("episodes", regex.compile(r"(?:\b[ée]p?(?:isode)?|[Ээ]пизод|[Сс]ер(?:ии|ия|\.)?|cap(?:itulo)?|epis[oó]dio)[. ]?[-:#№]?[. ]?(\d{1,4})(?:[abc]|v0?[1-4]|\W|$)", regex.IGNORECASE), array(integer))
    parser.add_handler("episodes", regex.compile(r"\b(\d{1,3})(?:-?я)?[ ._-]*(?:ser(?:i?[iyj]a|\b)|[Сс]ер(?:ии|ия|\.)?)", regex.IGNORECASE), array(integer))
    parser.add_handler("episodes", regex.compile(r"(?:\D|^)\d{1,2}[. ]?[xх][. ]?(\d{1,3})(?:[abc]|v0?[1-4]|\D|$)"), array(integer))  # Fixed: Was catching `1.x265` as episode.
    parser.add_handler("episodes", regex.compile(r"(?<=S\d{2}E)\d+", regex.IGNORECASE), array(integer))
    parser.add_handler("episodes", regex.compile(r"[[(]\d{1,2}\.(\d{1,3})[)\]]"), array(integer))
    parser.add_handler("episodes", regex.compile(r"\b[Ss]\d{1,2}[ .](\d{1,2})\b"), array(integer))
    parser.add_handler("episodes", regex.compile(r"-\s?\d{1,2}\.(\d{2,3})\s?-"), array(integer))
    parser.add_handler("episodes", regex.compile(r"(?<=\D|^)(\d{1,3})[. ]?(?:of|из|iz)[. ]?\d{1,3}(?=\D|$)", regex.IGNORECASE), array(integer))
    parser.add_handler("episodes", regex.compile(r"\b\d{2}[ ._-](\d{2})(?:.F)?\.\w{2,4}$"), array(integer))
    parser.add_handler("episodes", regex.compile(r"(?<!^)\[(?!720|1080)(\d{2,3})](?!(?:\.\w{2,4})?$)"), array(integer))
    parser.add_handler("episodes", regex.compile(r"(\d+)(?=.?\[([A-Z0-9]{8})])", regex.IGNORECASE), array(integer))
    parser.add_handler("episodes", regex.compile(r"(?<![xh])\b264\b|\b265\b", regex.IGNORECASE), array(integer), {"remove": True})
    parser.add_handler("episodes", regex.compile(r"(?<!\bMovie\s-\s)(?<=\s-\s)\d+(?=\s[-(\s])"), array(integer), {"remove": True, "skipIfAlreadyFound": True})
    parser.add_handler("episodes", regex.compile(r"(?:\W|^)(?:\d+)?(?:e|ep)(\d{1,3})(?:\W|$)", regex.IGNORECASE), array(integer), {"remove": True})
    parser.add_handler("episodes", regex.compile(r"\d+.-.\d+TV", regex.IGNORECASE), range_func, {"remove": True})


    # Oryginał: r"(?:[\W\d]|^)\d+[xх][ .]?[([]?(\d{1,3}(?:[ .]?[xх][ .]?\d{1,3})+)(?:\W|$)" (rosyjskie 'х')
    # Polski odpowiednik: "x" lub "odc"
    parser.add_handler("episodes", regex.compile(r"(?:[\W\d]|^)\d+(?:x|odc)[ .]?[([]?(\d{1,3}(?:[ .]?(?:x|odc)[ .]?\d{1,3})+)(?:\W|$)", regex.IGNORECASE), range_func)

    # Oryginał: r"(?:[\W\d]|^)(?:episodes?|[Сс]ерии:?)[ .]?[([]?(\d{1,3}(?:[ .+]*[&+][ .]?\d{1,3})+)(?:\W|$)" (rosyjskie 'серии')
    # Polski odpowiednik: "odcinki"
    parser.add_handler("episodes", regex.compile(r"(?:[\W\d]|^)(?:odcinki?|odc\.?)[ .]?[([]?(\d{1,3}(?:[ .+]*[&+][ .]?\d{1,3})+)(?:\W|$)", regex.IGNORECASE), range_func)

    # Oryginał: r"[([]?(?:\D|^)(\d{1,3}[ .]?ao[ .]?\d{1,3})[)\]]?(?:\W|$)" ('ao' może być 'až po' - czeski/słowacki, lub 'até o' - portugalski)
    # Polski odpowiednik: "do" lub "-"
    parser.add_handler("episodes", regex.compile(r"[([]?(?:\D|^)(\d{1,3}[ .]?(?:do|-)[ .]?\d{1,3})[)\]]?(?:\W|$)", regex.IGNORECASE), range_func)

    # Oryginał: r"(?:[\W\d]|^)(?:e|eps?|episodes?|[Сс]ерии:?|\d+[xх])[ .]*[([]?(\d{1,3}(?:-\d{1,3})+)(?:\W|$)" (rosyjskie)
    # Polski odpowiednik: "o" (odcinek), "odc", "odcinki"
    parser.add_handler("episodes", regex.compile(r"(?:[\W\d]|^)(?:o|odc\.?|odcinki?|\d+(?:x|odc))[ .]*[([]?(\d{1,3}(?:-\d{1,3})+)(?:\W|$)", regex.IGNORECASE), range_func)

    # Oryginał: r"[st]\d{1,2}[. ]?[xх-]?[. ]?(?:e|x|х|ep|-|\.)[. ]?(\d{1,4})(?:[abc]|v0?[1-4]|\D|$)" (rosyjskie 'х')
    parser.add_handler("episodes", regex.compile(r"[st]\d{1,2}[. ]?(?:x|odc|-)?[. ]?(?:o|odc|x|ep|-|\.)[. ]?(\d{1,4})(?:[abc]|v0?[1-4]|\D|$)", regex.IGNORECASE), array(integer), {"remove": True})

    # Oryginał: r"(?:\W|^)(\d{1,3}(?:[ .]*~[ .]*\d{1,3})+)(?:\W|$)" ('~' jako 'do')
    parser.add_handler("episodes", regex.compile(r"(?:\W|^)(\d{1,3}(?:[ .]*(?:-|do)[ .]*\d{1,3})+)(?:\W|$)", regex.IGNORECASE), range_func)

    # Oryginał: r"(?<!(?:seasons?|[Сс]езони?)\W*)(?:[ .([-]|^)(\d{1,3}(?:[ .]?[,&+~][ .]?\d{1,3})+)(?:[ .)\]-]|$)" (rosyjskie 'сезони')
    parser.add_handler("episodes", regex.compile(r"(?<!(?:sezon(?:y|u|ów)?)\W*)(?:[ .([-]|^)(\d{1,3}(?:[ .]?(?:,|i|oraz|&|\+|do|-)[ .]?\d{1,3})+)(?:[ .)\]-]|$)", regex.IGNORECASE), range_func)
    parser.add_handler("episodes", regex.compile(r"(?<!(?:sezon(?:y|u|ow)?)\W*)(?:[ .([-]|^)(\d{1,3}(?:[ .]?(?:,|i|oraz|&|\+|do|-)[ .]?\d{1,3})+)(?:[ .)\]-]|$)", regex.IGNORECASE), range_func)

    # Oryginał: r"(?<!(?:seasons?|[Сс]езони?)\W*)(?:[ .([-]|^)(\d{1,3}(?:-\d{1,3})+)(?:[ .)(\]]|-\D|$)" (rosyjskie)
    parser.add_handler("episodes", regex.compile(r"(?<!(?:sezon(?:y|u|ów)?)\W*)(?:[ .([-]|^)(\d{1,3}(?:-\d{1,3})+)(?:[ .)(\]]|-\D|$)", regex.IGNORECASE), range_func)
    parser.add_handler("episodes", regex.compile(r"(?<!(?:sezon(?:y|u|ow)?)\W*)(?:[ .([-]|^)(\d{1,3}(?:-\d{1,3})+)(?:[ .)(\]]|-\D|$)", regex.IGNORECASE), range_func)

    # Oryginał: r"(?:\b[ée]p?(?:isode)?|[Ээ]пизод|[Сс]ер(?:ии|ия|\.)?|cap(?:itulo)?|epis[oó]dio)[. ]?[-:#№]?[. ]?(\d{1,4})(?:[abc]|v0?[1-4]|\W|$)" (francuski, rosyjski, hiszpański/portugalski)
    # Polski odpowiednik: "odcinek", "odc", "część"
    parser.add_handler("episodes", regex.compile(r"(?:\b(?:odc\.?|odcinek|odcinki)|część|czesc)[. ]?[-:#№]?[. ]?(\d{1,4})(?:[abc]|v0?[1-4]|\W|$)", regex.IGNORECASE), array(integer))
    parser.add_handler("episodes", regex.compile(r"(?:\b(?:odc\.?|odcinek|odcinki)|czesc)[. ]?[-:#№]?[. ]?(\d{1,4})(?:[abc]|v0?[1-4]|\W|$)", regex.IGNORECASE), array(integer))


    # Oryginał: r"\b(\d{1,3})(?:-?я)?[ ._-]*(?:ser(?:i?[iyj]a|\b)|[Сс]ер(?:ии|ия|\.)?)" (rosyjskie/serbskie)
    # Polski odpowiednik: "1-szy odcinek/seria"
    parser.add_handler("episodes", regex.compile(r"\b(\d{1,3})(?:-?(?:szy|gi|ci|ty|my|wy|ga|cia|ta|ma|wa))?[ ._-]*(?:odc\.?|odcinek|seria)", regex.IGNORECASE), array(integer))

    # Oryginał: r"(?:\D|^)\d{1,2}[. ]?[xх][. ]?(\d{1,3})(?:[abc]|v0?[1-4]|\D|$)" (rosyjskie 'х')
    parser.add_handler("episodes", regex.compile(r"(?:\D|^)\d{1,2}[. ]?(?:x|odc)[. ]?(\d{1,3})(?:[abc]|v0?[1-4]|\D|$)", regex.IGNORECASE), array(integer))

    # Oryginał: r"(?<=\D|^)(\d{1,3})[. ]?(?:of|из|iz)[. ]?\d{1,3}(?=\D|$)" (angielskie 'of', rosyjskie 'из', inne słowiańskie 'iz')
    # Polski odpowiednik: "z"
    parser.add_handler("episodes", regex.compile(r"(?<=\D|^)(\d{1,3})[. ]?(?:z)[. ]?\d{1,3}(?=\D|$)", regex.IGNORECASE), array(integer))


    def handle_episodes(context):
        title = context["title"]
        result = context.get("result", {})
        matched = context.get("matched", {})

        if "episodes" not in result:
            start_indexes = [comp.get("match_index") for comp in [matched.get("year"), matched.get("seasons")] if comp and comp.get("match_index", None)]
            end_indexes = [comp["match_index"] for comp in [matched.get("resolution"), matched.get("quality"), matched.get("codec"), matched.get("audio")] if comp and comp.get("match_index", None)]

            start_index = min(start_indexes) if start_indexes else 0
            end_index = min(end_indexes + [len(title)])

            beginning_title = title[:end_index]
            middle_title = title[start_index:end_index]

            beginning_pattern = regex.compile(r"(?<!movie\W*|film\W*|^)(?:[ .]+-[ .]+|[([][ .]*)(\d{1,4})(?:a|b|v\d|\.\d)?(?:\W|$)(?!movie|film|\d+)(?<!\[(?:480|720|1080)\])", regex.IGNORECASE)
            middle_pattern = regex.compile(r"^(?:[([-][ .]?)?(\d{1,4})(?:a|b|v\d)?(?:\W|$)(?!movie|film)(?!\[(480|720|1080)\])", regex.IGNORECASE)
            matches = beginning_pattern.search(beginning_title) or middle_pattern.search(middle_title)

            if matches:
                # PO DOPASOWANIU: pozwól sufiksy epów (a, b, v\d, .\d),
                # ale odrzuć, gdy po liczbie zaczyna się słowo z ≥3 liter (np. "Years")
                after_src = beginning_title if matches.re is beginning_pattern else middle_title
                after = after_src[matches.end(1):]  # wszystko po złapanej liczbie
            
                allowed_suffix = regex.compile(r"\s*(?:a|b|v\d+|\.\d+)(?:\W|$)", regex.IGNORECASE)
            
                if allowed_suffix.match(after):
                    pass  # prawdziwy ep: 12a, 10b, 22v2, 03.1 itd.
                elif regex.match(r"\s*[A-Za-zĄĆĘŁŃÓŚŹŻąćęłńóśźż]{3,}", after):
                    return None  # zaczyna się słowo 3+ liter (" Years"), więc to nie epizod
            
                episode_numbers = [int(num) for num in regex.findall(r"\d+", matches.group(1))]
                result["episodes"] = episode_numbers
                return {"match_index": title.index(matches.group(0))}

        return None

    parser.add_handler("episodes", handle_episodes, {"skipIfAlreadyFound": True})

    # Country Code
    parser.add_handler("country", regex.compile(r"\b(US|UK|AU|NZ|CA)\b"), value("$1"))

    # Languages (ISO 639-1 Standardized)
    parser.add_handler("languages", regex.compile(r"\bengl?(?:sub[A-Z]*)?\b", regex.IGNORECASE), uniq_concat(value("en")), {"remove": True, "skipIfAlreadyFound": False})
    parser.add_handler("languages", regex.compile(r"\beng?sub[A-Z]*\b", regex.IGNORECASE), uniq_concat(value("en")), {"skipIfAlreadyFound": False})
    parser.add_handler("languages", regex.compile(r"\bing(?:l[eéê]s)?\b", regex.IGNORECASE), uniq_concat(value("en")), {"skipIfAlreadyFound": False})
    parser.add_handler("languages", regex.compile(r"\besub\b", regex.IGNORECASE), uniq_concat(value("en")), {"remove": True, "skipIfAlreadyFound": False})
    parser.add_handler("languages", regex.compile(r"\benglish\W+(?:subs?|sdh|hi)\b", regex.IGNORECASE), uniq_concat(value("en")), {"skipIfAlreadyFound": False})
    parser.add_handler("languages", regex.compile(r"\beng?\b", regex.IGNORECASE), uniq_concat(value("en")), {"skipFromTitle": True, "skipIfAlreadyFound": False})
    parser.add_handler("languages", regex.compile(r"\benglish?\b", regex.IGNORECASE), uniq_concat(value("en")), {"skipIfFirst": True, "skipIfAlreadyFound": False})
    parser.add_handler("languages", regex.compile(r"\b(?:JP|JAP|JPN)\b", regex.IGNORECASE), uniq_concat(value("ja")), {"skipIfAlreadyFound": False})
    parser.add_handler("languages", regex.compile(r"\b(japanese|japon[eê]s)\b", regex.IGNORECASE), uniq_concat(value("ja")), {"skipIfFirst": True, "skipIfAlreadyFound": False})
    parser.add_handler("languages", regex.compile(r"\b(?:KOR|kor[ .-]?sub)\b", regex.IGNORECASE), uniq_concat(value("ko")), {"skipIfAlreadyFound": False})
    parser.add_handler("languages", regex.compile(r"\b(korean|coreano)\b", regex.IGNORECASE), uniq_concat(value("ko")), {"skipIfFirst": True, "skipIfAlreadyFound": False})
    parser.add_handler("languages", regex.compile(r"\b(?:traditional\W*chinese|chinese\W*traditional)(?:\Wchi)?\b", regex.IGNORECASE), uniq_concat(value("zh")), {"skipIfAlreadyFound": False, "remove": True})
    parser.add_handler("languages", regex.compile(r"\bzh-hant\b", regex.IGNORECASE), uniq_concat(value("zh")), {"skipIfAlreadyFound": False})
    parser.add_handler("languages", regex.compile(r"\b(?:mand[ae]rin|ch[sn])\b", regex.IGNORECASE), uniq_concat(value("zh")), {"skipIfAlreadyFound": False})
    parser.add_handler("languages", regex.compile(r"(?<!shang-?)\bCH(?:I|T)\b", regex.IGNORECASE), uniq_concat(value("zh")), {"skipFromTitle": True, "skipIfAlreadyFound": False})
    parser.add_handler("languages", regex.compile(r"\b(chinese|chin[eê]s)\b", regex.IGNORECASE), uniq_concat(value("zh")), {"skipIfFirst": True, "skipIfAlreadyFound": False})
    parser.add_handler("languages", regex.compile(r"\bzh-hans\b", regex.IGNORECASE), uniq_concat(value("zh")), {"skipIfAlreadyFound": False})
    parser.add_handler("languages", regex.compile(r"\bFR(?:a|e|anc[eê]s|VF[FQIB2]?)\b", regex.IGNORECASE), uniq_concat(value("fr")), {"skipFromTitle": True, "skipIfAlreadyFound": False})
    parser.add_handler("languages", regex.compile(r"\b\[?(VF[FQRIB2]?\]?\b|(VOST)?FR2?)\b"), uniq_concat(value("fr")), {"remove": True, "skipIfAlreadyFound": False})
    parser.add_handler("languages", regex.compile(r"\b(TRUE|SUB).?FRENCH\b|\bFRENCH\b|\bFre?\b"), uniq_concat(value("fr")), {"remove": True, "skipIfAlreadyFound": False})
    parser.add_handler("languages", regex.compile(r"\b(VOST(?:FR?|A)?)\b", regex.IGNORECASE), uniq_concat(value("fr")), {"skipIfAlreadyFound": False})
    # parser.add_handler("languages", regex.compile(r"\b(VF[FQIB2]?|(TRUE|SUB).?FRENCH|(VOST)?FR2?)\b", regex.IGNORECASE), uniq_concat(value("fr")), {"remove": True, "skipIfAlreadyFound": True})
    parser.add_handler("languages", regex.compile(r"\bspanish\W?latin|american\W*(?:spa|esp?)", regex.IGNORECASE), uniq_concat(value("la")), {"skipFromTitle": True, "skipIfAlreadyFound": False, "remove": True})
    parser.add_handler("languages", regex.compile(r"\b(?:\bla\b.+(?:cia\b))", regex.IGNORECASE), uniq_concat(value("es")), {"skipFromTitle": True, "skipIfAlreadyFound": False})
    parser.add_handler("languages", regex.compile(r"\b(?:audio.)?lat(?:in?|ino)?\b", regex.IGNORECASE), uniq_concat(value("la")), {"skipIfAlreadyFound": False})
    parser.add_handler("languages", regex.compile(r"\b(?:audio.)?(?:ESP?|spa|(en[ .]+)?espa[nñ]ola?|castellano)\b", regex.IGNORECASE), uniq_concat(value("es")), {"skipIfAlreadyFound": False})
    parser.add_handler("languages", regex.compile(r"\bes(?=[ .,/-]+(?:[A-Z]{2}[ .,/-]+){2,})\b", regex.IGNORECASE), uniq_concat(value("es")), {"skipFromTitle": True, "skipIfAlreadyFound": False})
    parser.add_handler("languages", regex.compile(r"\b(?<=[ .,/-]+(?:[A-Z]{2}[ .,/-]+){2,})es\b", regex.IGNORECASE), uniq_concat(value("es")), {"skipFromTitle": True, "skipIfAlreadyFound": False})
    parser.add_handler("languages", regex.compile(r"\b(?<=[ .,/-]+[A-Z]{2}[ .,/-]+)es(?=[ .,/-]+[A-Z]{2}[ .,/-]+)\b", regex.IGNORECASE), uniq_concat(value("es")), {"skipFromTitle": True, "skipIfAlreadyFound": False})
    parser.add_handler("languages", regex.compile(r"\bes(?=\.(?:ass|ssa|srt|sub|idx)$)", regex.IGNORECASE), uniq_concat(value("es")), {"skipFromTitle": True, "skipIfAlreadyFound": False})
    parser.add_handler("languages", regex.compile(r"\bspanish\W+subs?\b", regex.IGNORECASE), uniq_concat(value("es")), {"skipIfAlreadyFound": False})
    parser.add_handler("languages", regex.compile(r"\b(spanish|espanhol)\b", regex.IGNORECASE), uniq_concat(value("es")), {"skipIfFirst": True, "skipIfAlreadyFound": False})
    parser.add_handler("languages", regex.compile(r"\b[\.\s\[]?Sp[\.\s\]]?\b", regex.IGNORECASE), uniq_concat(value("es")), {"remove": True, "skipIfAlreadyFound": False})
    parser.add_handler("languages", regex.compile(r"\b(?:p[rt]|en|port)[. (\\/-]*BR\b", regex.IGNORECASE), uniq_concat(value("pt")), {"skipIfAlreadyFound": False, "remove": True})
    parser.add_handler("languages", regex.compile(r"\bbr(?:a|azil|azilian)\W+(?:pt|por)\b", regex.IGNORECASE), uniq_concat(value("pt")), {"skipIfAlreadyFound": False, "remove": True})
    parser.add_handler("languages", regex.compile(r"\b(?:leg(?:endado|endas?)?|dub(?:lado)?|portugu[eèê]se?)[. -]*BR\b", regex.IGNORECASE), uniq_concat(value("pt")), {"skipIfAlreadyFound": False})
    parser.add_handler("languages", regex.compile(r"\bleg(?:endado|endas?)\b", regex.IGNORECASE), uniq_concat(value("pt")), {"skipIfAlreadyFound": False})
    parser.add_handler("languages", regex.compile(r"\bportugu[eèê]s[ea]?\b", regex.IGNORECASE), uniq_concat(value("pt")), {"skipIfAlreadyFound": False})
    parser.add_handler("languages", regex.compile(r"\bPT[. -]*(?:PT|ENG?|sub(?:s|titles?))\b", regex.IGNORECASE), uniq_concat(value("pt")), {"skipIfAlreadyFound": False})
    parser.add_handler("languages", regex.compile(r"\bpt(?=\.(?:ass|ssa|srt|sub|idx)$)", regex.IGNORECASE), uniq_concat(value("pt")), {"skipFromTitle": True, "skipIfAlreadyFound": False})
    parser.add_handler("languages", regex.compile(r"\bPT\b", regex.IGNORECASE), uniq_concat(value("pt")), {"remove": True, "skipIfAlreadyFound": False})
    parser.add_handler("languages", regex.compile(r"\bpor\b", regex.IGNORECASE), uniq_concat(value("pt")), {"skipFromTitle": True, "skipIfAlreadyFound": False})
    parser.add_handler("languages", regex.compile(r"\b-?ITA\b", regex.IGNORECASE), uniq_concat(value("it")), {"remove": True, "skipIfAlreadyFound": False})
    parser.add_handler("languages", regex.compile(r"\b(?<!w{3}\.\w+\.)IT(?=[ .,/-]+(?:[a-zA-Z]{2}[ .,/-]+){2,})\b"), uniq_concat(value("it")), {"skipFromTitle": True, "skipIfAlreadyFound": False})
    parser.add_handler("languages", regex.compile(r"\bit(?=\.(?:ass|ssa|srt|sub|idx)$)", regex.IGNORECASE), uniq_concat(value("it")), {"skipFromTitle": True, "skipIfAlreadyFound": False})
    parser.add_handler("languages", regex.compile(r"\bitaliano?\b", regex.IGNORECASE), uniq_concat(value("it")), {"skipIfFirst": True, "skipIfAlreadyFound": False})
    parser.add_handler("languages", regex.compile(r"\bgreek[ .-]*(?:audio|lang(?:uage)?|subs?(?:titles?)?)?\b", regex.IGNORECASE), uniq_concat(value("el")), {"skipIfFirst": True, "skipIfAlreadyFound": False})
    parser.add_handler("languages", regex.compile(r"\b(?:GER|DEU)\b", regex.IGNORECASE), uniq_concat(value("de")), {"skipFromTitle": True, "skipIfAlreadyFound": False})
    parser.add_handler("languages", regex.compile(r"\bde(?=[ .,/-]+(?:[A-Z]{2}[ .,/-]+){2,})\b", regex.IGNORECASE), uniq_concat(value("de")), {"skipFromTitle": True, "skipIfAlreadyFound": False})
    parser.add_handler("languages", regex.compile(r"\b(?<=[ .,/-]+(?:[A-Z]{2}[ .,/-]+){2,})de\b", regex.IGNORECASE), uniq_concat(value("de")), {"skipFromTitle": True, "skipIfAlreadyFound": False})
    parser.add_handler("languages", regex.compile(r"\b(?<=[ .,/-]+[A-Z]{2}[ .,/-]+)de(?=[ .,/-]+[A-Z]{2}[ .,/-]+)\b", regex.IGNORECASE), uniq_concat(value("de")), {"skipFromTitle": True, "skipIfAlreadyFound": False})
    parser.add_handler("languages", regex.compile(r"\bde(?=\.(?:ass|ssa|srt|sub|idx)$)", regex.IGNORECASE), uniq_concat(value("de")), {"skipFromTitle": True, "skipIfAlreadyFound": False})
    parser.add_handler("languages", regex.compile(r"\b(german|alem[aã]o)\b", regex.IGNORECASE), uniq_concat(value("de")), {"skipIfFirst": True, "skipIfAlreadyFound": False})
    parser.add_handler("languages", regex.compile(r"\bRUS?\b", regex.IGNORECASE), uniq_concat(value("ru")), {"skipIfAlreadyFound": False})
    parser.add_handler("languages", regex.compile(r"\b(russian|russo)\b", regex.IGNORECASE), uniq_concat(value("ru")), {"skipIfFirst": True, "skipIfAlreadyFound": False})
    parser.add_handler("languages", regex.compile(r"\bUKR\b", regex.IGNORECASE), uniq_concat(value("uk")), {"skipIfAlreadyFound": False})
    parser.add_handler("languages", regex.compile(r"\bukrainian\b", regex.IGNORECASE), uniq_concat(value("uk")), {"skipIfFirst": True, "skipIfAlreadyFound": False})
    parser.add_handler("languages", regex.compile(r"\bhin(?:di)?\b", regex.IGNORECASE), uniq_concat(value("hi")), {"skipIfAlreadyFound": False})
    parser.add_handler("languages", regex.compile(r"\b(?:(?<!w{3}\.\w+\.)tel(?!\W*aviv)|telugu)\b", regex.IGNORECASE), uniq_concat(value("te")), {"remove": True, "skipIfAlreadyFound": False})
    parser.add_handler("languages", regex.compile(r"\bt[aâ]m(?:il)?\b", regex.IGNORECASE), uniq_concat(value("ta")), {"remove": True, "skipIfAlreadyFound": False})
    parser.add_handler("languages", regex.compile(r"\b(?:(?<!w{3}\.\w+\.)MAL(?:ay)?|malayalam)\b", regex.IGNORECASE), uniq_concat(value("ml")), {"remove": True, "skipIfFirst": True, "skipIfAlreadyFound": False})
    parser.add_handler("languages", regex.compile(r"\b(?:(?<!w{3}\.\w+\.)KAN(?:nada)?|kannada)\b", regex.IGNORECASE), uniq_concat(value("kn")), {"remove": True, "skipIfAlreadyFound": False})
    parser.add_handler("languages", regex.compile(r"\b(?:(?<!w{3}\.\w+\.)MAR(?:a(?:thi)?)?|marathi)\b", regex.IGNORECASE), uniq_concat(value("mr")), {"skipIfAlreadyFound": False})
    parser.add_handler("languages", regex.compile(r"\b(?:(?<!w{3}\.\w+\.)GUJ(?:arati)?|gujarati)\b", regex.IGNORECASE), uniq_concat(value("gu")), {"skipIfAlreadyFound": False})
    parser.add_handler("languages", regex.compile(r"\b(?:(?<!w{3}\.\w+\.)PUN(?:jabi)?|punjabi)\b", regex.IGNORECASE), uniq_concat(value("pa")), {"skipIfAlreadyFound": False})
    parser.add_handler("languages", regex.compile(r"\b(?:(?<!w{3}\.\w+\.)BEN(?!.\bThe|and|of\b)(?:gali)?|bengali)\b", regex.IGNORECASE), uniq_concat(value("bn")), {"skipIfFirst": True, "skipIfAlreadyFound": False})
    parser.add_handler("languages", regex.compile(r"\b(?<!YTS\.)LT\b"), uniq_concat(value("lt")), {"skipFromTitle": True, "skipIfAlreadyFound": False})
    parser.add_handler("languages", regex.compile(r"\blithuanian\b", regex.IGNORECASE), uniq_concat(value("lt")), {"skipIfFirst": True, "skipIfAlreadyFound": False})
    parser.add_handler("languages", regex.compile(r"\blatvian\b", regex.IGNORECASE), uniq_concat(value("lv")), {"skipIfFirst": True, "skipIfAlreadyFound": False})
    parser.add_handler("languages", regex.compile(r"\bestonian\b", regex.IGNORECASE), uniq_concat(value("et")), {"skipIfFirst": True, "skipIfAlreadyFound": False})
    parser.add_handler("languages", regex.compile(r"\b(polish|polon[eê]s|polaco)\b", regex.IGNORECASE), uniq_concat(value("pl")), {"skipIfFirst": True, "skipIfAlreadyFound": False})
    # Frazy typu "serial polski", "polski serial", "film polski", "polski film"
    # (zamiast spacji mogą być kropki) → język PL i USUWAMY z tytułu.
    parser.add_handler(
        "languages",
        regex.compile(r"\b(?:serial|film)[ .]polski\b", regex.IGNORECASE),
        uniq_concat(value("pl")),
        {"remove": True, "skipIfAlreadyFound": False}
    )
    parser.add_handler(
        "languages",
        regex.compile(r"\bpolski[ .](?:serial|film)\b", regex.IGNORECASE),
        uniq_concat(value("pl")),
        {"remove": True, "skipIfAlreadyFound": False}
    )
    parser.add_handler(
        "languages",
        regex.compile(
            r"""
            \b(?:
                  PLDUB(?![\s._\-|\]\)\(\[\}\{]*MD\b)
                | DUBPL(?![\s._\-|\]\)\(\[\}\{]*MD\b)
                | DubbingPL(?![\s._\-|\]\)\(\[\}\{]*MD\b)
                | PLDubbing(?![\s._\-|\]\)\(\[\}\{]*MD\b)
                | LekPL
                | LektorPL
                | PLLektor
                | Lektor
            )\b
            """,
            regex.IGNORECASE | regex.VERBOSE
        ),
        uniq_concat(value("pl")),
        {"remove": True, "skipIfAlreadyFound": False}
    )
    parser.add_handler(
        "languages",
        regex.compile(r"(Polski Dubbing|Dubbing ?i ?napisy|Dubbing ?DDP ?5.1 ?i ?Napisy|Dubbing ?5.1 ?i ?Napisy|Dubbing ?DDP ?i ?Napisy|Dubbing ?DD ?5.1 ?i ?Napisy)", regex.IGNORECASE),
        uniq_concat(value("pl")),
        {"remove": True, "skipIfAlreadyFound": False}
    )
    parser.add_handler("languages", regex.compile(r"\bCZ[EH]?\b", regex.IGNORECASE), uniq_concat(value("cs")), {"skipIfFirst": True, "skipIfAlreadyFound": False})
    parser.add_handler("languages", regex.compile(r"\bczech\b", regex.IGNORECASE), uniq_concat(value("cs")), {"skipIfFirst": True, "skipIfAlreadyFound": False})
    parser.add_handler("languages", regex.compile(r"\bslo(?:vak|vakian|subs|[\]_)]?\.\w{2,4}$)\b", regex.IGNORECASE), uniq_concat(value("sk")), {"skipFromTitle": True, "skipIfAlreadyFound": False})
    parser.add_handler("languages", regex.compile(r"\bHU\b"), uniq_concat(value("hu")), {"skipFromTitle": True, "skipIfAlreadyFound": False})
    parser.add_handler("languages", regex.compile(r"\bHUN(?:garian)?\b", regex.IGNORECASE), uniq_concat(value("hu")), {"skipFromTitle": True, "skipIfAlreadyFound": False})
    parser.add_handler("languages", regex.compile(r"\bROM(?:anian)?\b", regex.IGNORECASE), uniq_concat(value("ro")), {"skipFromTitle": True, "skipIfAlreadyFound": False})
    parser.add_handler("languages", regex.compile(r"\bRO(?=[ .,/-]*(?:[A-Z]{2}[ .,/-]+)*sub)", regex.IGNORECASE), uniq_concat(value("ro")), {"skipIfAlreadyFound": False})
    parser.add_handler("languages", regex.compile(r"\bbul(?:garian)?\b", regex.IGNORECASE), uniq_concat(value("bg")), {"skipFromTitle": True, "skipIfAlreadyFound": False})
    parser.add_handler("languages", regex.compile(r"\b(?:srp|serbian)\b", regex.IGNORECASE), uniq_concat(value("sr")), {"skipIfAlreadyFound": False})
    parser.add_handler("languages", regex.compile(r"\b(?:HRV|croatian)\b", regex.IGNORECASE), uniq_concat(value("hr")), {"skipIfAlreadyFound": False})
    parser.add_handler("languages", regex.compile(r"\bHR(?=[ .,/-]*(?:[A-Z]{2}[ .,/-]+)*sub)\b", regex.IGNORECASE), uniq_concat(value("hr")), {"skipIfAlreadyFound": False})
    parser.add_handler("languages", regex.compile(r"\bslovenian\b", regex.IGNORECASE), uniq_concat(value("sl")), {"skipFromTitle": True, "skipIfAlreadyFound": False})
    parser.add_handler("languages", regex.compile(r"\b(?:(?<!w{3}\.\w+\.)NL|dut|holand[eê]s)\b", regex.IGNORECASE), uniq_concat(value("nl")), {"skipIfAlreadyFound": False})
    parser.add_handler("languages", regex.compile(r"\bdutch\b", regex.IGNORECASE), uniq_concat(value("nl")), {"skipFromTitle": True, "skipIfAlreadyFound": False})
    parser.add_handler("languages", regex.compile(r"\bflemish\b", regex.IGNORECASE), uniq_concat(value("nl")), {"skipIfAlreadyFound": False})
    parser.add_handler("languages", regex.compile(r"\b(?:DK|danska|dansub|nordic)\b", regex.IGNORECASE), uniq_concat(value("da")), {"skipIfAlreadyFound": False})
    parser.add_handler("languages", regex.compile(r"\b(danish|dinamarqu[eê]s)\b", regex.IGNORECASE), uniq_concat(value("da")), {"skipFromTitle": True, "skipIfAlreadyFound": False})
    parser.add_handler("languages", regex.compile(r"\bdan\b(?=.*\.(?:srt|vtt|ssa|ass|sub|idx)$)", regex.IGNORECASE), uniq_concat(value("da")), {"skipFromTitle": True, "skipIfAlreadyFound": False})
    parser.add_handler("languages", regex.compile(r"\b(?:(?<!w{3}\.\w+\.|Sci-)FI|finsk|finsub|nordic)\b", regex.IGNORECASE), uniq_concat(value("fi")), {"skipIfAlreadyFound": False})
    parser.add_handler("languages", regex.compile(r"\bfinnish\b", regex.IGNORECASE), uniq_concat(value("fi")), {"skipFromTitle": True, "skipIfAlreadyFound": False})
    parser.add_handler("languages", regex.compile(r"\b(?:(?<!w{3}\.\w+\.)SE|swe|swesubs?|sv(?:ensk)?|nordic)\b", regex.IGNORECASE), uniq_concat(value("sv")), {"skipIfAlreadyFound": False})
    parser.add_handler("languages", regex.compile(r"\b(swedish|sueco)\b", regex.IGNORECASE), uniq_concat(value("sv")), {"skipFromTitle": True, "skipIfAlreadyFound": False})
    parser.add_handler("languages", regex.compile(r"\b(?:NOR|norsk|norsub|nordic)\b", regex.IGNORECASE), uniq_concat(value("no")), {"skipIfAlreadyFound": False})
    parser.add_handler("languages", regex.compile(r"\b(norwegian|noruegu[eê]s|bokm[aå]l|nob|nor(?=[\]_)]?\.\w{2,4}$))\b", regex.IGNORECASE), uniq_concat(value("no")), {"skipFromTitle": True, "skipIfAlreadyFound": False})
    parser.add_handler("languages", regex.compile(r"\b(?:arabic|[aá]rabe|ara)\b", regex.IGNORECASE), uniq_concat(value("ar")), {"skipIfFirst": True, "skipIfAlreadyFound": False})
    parser.add_handler("languages", regex.compile(r"\barab.*(?:audio|lang(?:uage)?|sub(?:s|titles?)?)\b", regex.IGNORECASE), uniq_concat(value("ar")), {"skipFromTitle": True, "skipIfAlreadyFound": False})
    parser.add_handler("languages", regex.compile(r"\bar(?=\.(?:ass|ssa|srt|sub|idx)$)", regex.IGNORECASE), uniq_concat(value("ar")), {"skipFromTitle": True, "skipIfAlreadyFound": False})
    parser.add_handler("languages", regex.compile(r"\b(?:turkish|tur(?:co)?)\b", regex.IGNORECASE), uniq_concat(value("tr")), {"skipFromTitle": True, "skipIfAlreadyFound": False})
    parser.add_handler("languages", regex.compile(r"\b(TİVİBU|tivibu|bitturk(.net)?|turktorrent)\b", regex.IGNORECASE), uniq_concat(value("tr")), {"skipFromTitle": True, "skipIfAlreadyFound": False})
    parser.add_handler("languages", regex.compile(r"\bvietnamese\b|\bvie(?=[\]_)]?\.\w{2,4}$)", regex.IGNORECASE), uniq_concat(value("vi")), {"skipFromTitle": True, "skipIfAlreadyFound": False})
    parser.add_handler("languages", regex.compile(r"\bind(?:onesian)?\b", regex.IGNORECASE), uniq_concat(value("id")), {"skipFromTitle": True, "skipIfAlreadyFound": False})
    parser.add_handler("languages", regex.compile(r"\b(thai|tailand[eê]s)\b", regex.IGNORECASE), uniq_concat(value("th")), {"skipIfFirst": True, "skipIfAlreadyFound": False})
    parser.add_handler("languages", regex.compile(r"\b(THA|tha)\b"), uniq_concat(value("th")), {"skipFromTitle": True, "skipIfAlreadyFound": False})
    parser.add_handler("languages", regex.compile(r"\b(?:malay|may(?=[\]_)]?\.\w{2,4}$)|(?<=subs?\([a-z,]+)may)\b", regex.IGNORECASE), uniq_concat(value("ms")), {"skipIfFirst": True, "skipIfAlreadyFound": False})
    parser.add_handler("languages", regex.compile(r"\bheb(?:rew|raico)?\b", regex.IGNORECASE), uniq_concat(value("he")), {"skipFromTitle": True, "skipIfAlreadyFound": False})
    parser.add_handler("languages", regex.compile(r"\b(persian|persa)\b", regex.IGNORECASE), uniq_concat(value("fa")), {"skipFromTitle": True, "skipIfAlreadyFound": False})

    parser.add_handler("languages", regex.compile(r"[\u3040-\u30ff]+", regex.IGNORECASE), uniq_concat(value("ja")), {"skipFromTitle": True, "skipIfAlreadyFound": False})  # japanese
    parser.add_handler("languages", regex.compile(r"[\u3400-\u4dbf]+", regex.IGNORECASE), uniq_concat(value("zh")), {"skipFromTitle": True, "skipIfAlreadyFound": False})  # chinese
    parser.add_handler("languages", regex.compile(r"[\u4e00-\u9fff]+", regex.IGNORECASE), uniq_concat(value("zh")), {"skipFromTitle": True, "skipIfAlreadyFound": False})  # chinese
    parser.add_handler("languages", regex.compile(r"[\uf900-\ufaff]+", regex.IGNORECASE), uniq_concat(value("zh")), {"skipFromTitle": True, "skipIfAlreadyFound": False})  # chinese
    parser.add_handler("languages", regex.compile(r"[\uff66-\uff9f]+", regex.IGNORECASE), uniq_concat(value("ja")), {"skipFromTitle": True, "skipIfAlreadyFound": False})  # japanese
    parser.add_handler("languages", regex.compile(r"[\u0400-\u04ff]+", regex.IGNORECASE), uniq_concat(value("ru")), {"skipFromTitle": True, "skipIfAlreadyFound": False})  # russian
    parser.add_handler("languages", regex.compile(r"[\u0600-\u06ff]+", regex.IGNORECASE), uniq_concat(value("ar")), {"skipFromTitle": True, "skipIfAlreadyFound": False})  # arabic
    parser.add_handler("languages", regex.compile(r"[\u0750-\u077f]+", regex.IGNORECASE), uniq_concat(value("ar")), {"skipFromTitle": True, "skipIfAlreadyFound": False})  # arabic
    parser.add_handler("languages", regex.compile(r"[\u0c80-\u0cff]+", regex.IGNORECASE), uniq_concat(value("kn")), {"skipFromTitle": True, "skipIfAlreadyFound": False})  # kannada
    parser.add_handler("languages", regex.compile(r"[\u0d00-\u0d7f]+", regex.IGNORECASE), uniq_concat(value("ml")), {"skipFromTitle": True, "skipIfAlreadyFound": False})  # malayalam
    parser.add_handler("languages", regex.compile(r"[\u0e00-\u0e7f]+", regex.IGNORECASE), uniq_concat(value("th")), {"skipFromTitle": True, "skipIfAlreadyFound": False})  # thai
    parser.add_handler("languages", regex.compile(r"[\u0900-\u097f]+", regex.IGNORECASE), uniq_concat(value("hi")), {"skipFromTitle": True, "skipIfAlreadyFound": False})  # hindi
    parser.add_handler("languages", regex.compile(r"[\u0980-\u09ff]+", regex.IGNORECASE), uniq_concat(value("bn")), {"skipFromTitle": True, "skipIfAlreadyFound": False})  # bengali
    parser.add_handler("languages", regex.compile(r"[\u0a00-\u0a7f]+", regex.IGNORECASE), uniq_concat(value("gu")), {"skipFromTitle": True, "skipIfAlreadyFound": False})  # gujarati

    def infer_language_based_on_naming(context):
        title = context["title"]
        result = context["result"]
        matched = context["matched"]
        if "languages" not in result or not any(lang in result["languages"] for lang in ["pt", "es"]):
            # Checking if episode naming convention suggests Portuguese language
            if (matched.get("episodes") and regex.search(r"capitulo|ao", matched["episodes"].get("raw_match", ""), regex.IGNORECASE)) or regex.search(r"dublado", title, regex.IGNORECASE):
                result["languages"] = result.get("languages", []) + ["pt"]

        return None

    parser.add_handler("languages", infer_language_based_on_naming)

    # Subbed
    parser.add_handler("subbed", regex.compile(r"\bmulti(?:ple)?[ .-]*(?:su?$|sub\w*|dub\w*)\b|msub", regex.IGNORECASE), boolean, {"remove": True})
    parser.add_handler("subbed", regex.compile(r"\b(?:Official.*?|Dual-?)?sub(s|bed)?\b", regex.IGNORECASE), boolean, {"remove": True})

    # Dubbed
    parser.add_handler("dubbed", regex.compile(r"[\[(\s]?\bmulti(?:ple)?[ .-]*(?:lang(?:uages?)?|audio|VF2)\b\][\[(\s]?", regex.IGNORECASE), boolean, {"remove": True, "skipIfAlreadyFound": False})
    parser.add_handler("dubbed", regex.compile(r"\btri(?:ple)?[ .-]*(?:audio|dub\w*)\b", regex.IGNORECASE), boolean, {"skipIfAlreadyFound": False})
    parser.add_handler("dubbed", regex.compile(r"\bdual[ .-]*(?:au?$|[aá]udio|line)\b", regex.IGNORECASE), boolean, {"skipIfAlreadyFound": False})
    parser.add_handler("dubbed", regex.compile(r"\bdual\b(?![ .-]*sub)", regex.IGNORECASE), boolean, {"skipIfAlreadyFound": False})
    parser.add_handler("dubbed", regex.compile(r"\b(fan\s?dub)\b", regex.IGNORECASE), boolean, {"remove": True, "skipFromTitle": True})
    parser.add_handler("dubbed", regex.compile(r"\b(Fan.*)?(?:DUBBED|dublado|dubbing|DUBS?)\b", regex.IGNORECASE), boolean, {"remove": True})
    parser.add_handler("dubbed", regex.compile(r"\b(?!.*\bsub(s|bed)?\b)([ _\-\[(\.])?(dual|multi)([ _\-\[(\.])?(audio)\b", regex.IGNORECASE), boolean, {"remove": True})
    parser.add_handler("dubbed", regex.compile(r"\b(JAP?(anese)?|ZH)\+ENG?(lish)?|ENG?(lish)?\+(JAP?(anese)?|ZH)\b", regex.IGNORECASE), boolean, {"remove": True})
    parser.add_handler("dubbed", regex.compile(r"\bMULTi\b", regex.IGNORECASE), boolean, {"remove": True})

    def handle_group(context):
        result = context["result"]
        matched = context["matched"]
        if "group" in matched and matched["group"].get("raw_match", "").startswith("[") and matched["group"]["raw_match"].endswith("]"):
            end_index = matched["group"]["match_index"] + len(matched["group"]["raw_match"]) if "group" in matched else 0

            # Check if there's any overlap with other matched elements
            if any(key != "group" and matched[key]["match_index"] < end_index for key in matched if "match_index" in matched[key]) and "group" in result:
                del result["group"]
        return None

    parser.add_handler("group", handle_group)

    # 3D
    parser.add_handler("3d", regex.compile(r"(?<=\b[12]\d{3}\b).*\b(3d|sbs|half[ .-]ou|half[ .-]sbs)\b", regex.IGNORECASE), boolean, {"remove": False, "skipIfFirst": True})
    parser.add_handler("3d", regex.compile(r"\b((Half.)?SBS|HSBS)\b", regex.IGNORECASE), boolean, {"remove": False, "skipIfFirst": True})
    parser.add_handler("3d", regex.compile(r"\bBluRay3D\b", regex.IGNORECASE), boolean, {"remove": False, "skipIfFirst": True})
    parser.add_handler("3d", regex.compile(r"\bBD3D\b", regex.IGNORECASE), boolean, {"remove": False, "skipIfFirst": True})
    parser.add_handler("3d", regex.compile(r"\b3D\b", regex.IGNORECASE), boolean, {"remove": False, "skipIfFirst": True})

    # Size
    parser.add_handler("size", regex.compile(r"\b(\d+(\.\d+)?\s?(MB|GB|TB))\b", regex.IGNORECASE), none, {"remove": True})

    # Site
    parser.add_handler("site", regex.compile(r"\b((?:www?.?)?(?:\w+\-)?\w+[\.\s](?:tv|party|in))\b(?:\s*-\s*|\s*[\]\)\}]\s*)", regex.IGNORECASE), value("$1"), {"remove": True})
    parser.add_handler("site", regex.compile(r"\b(?:www?.?)?(?:\w+\-)?\w+[\.\s](?:com|org|net|ms|mx|co|vip|nu|pics|eu)\b", regex.IGNORECASE), value("$1"), {"remove": True})
    parser.add_handler("site", regex.compile(r"rarbg|torrentleech|(?:the)?piratebay", regex.IGNORECASE), value("$1"), {"remove": True})
    parser.add_handler("site", regex.compile(r"\[([^\]]+\.[^\]]+)\](?=\.\w{2,4}$|\s)", regex.IGNORECASE), value("$1"), {"remove": True})
    parser.add_handler(
        "languages",
        regex.compile(
            r"""
            # wyjątek: nie łap 'PL|pol', jeśli wcześniej było "napisy ... multi ... (PL|pol)"
            # przykłady, które mają NIE ustawiać languages=pl:
            #   "Napisy-Multi PL", "napisy.multi.PL", "[napisy|multi|pl]"
            (?<!(?:napisy[\s._\-|\]\)\(\[\}\{]*multi[\s._\-|\]\)\(\[\}\{]*))
    
            # NOWY WYJĄTEK: nie łap 'PL|pol', jeśli wcześniej było "napisy ... multi ... <cyfra> ... (PL|pol)"
            # przykłady:
            #   "Napisy.Multi.1.PL", "napisy-multi-2-pl", "[napisy|multi|3|PL]"
            (?<!(?:napisy[\s._\-|\]\)\(\[\}\{]*multi[\s._\-|\]\)\(\[\}\{]*\d+[\s._\-|\]\)\(\[\}\{]*))
    
            # wyjątek: nie łap 'PL|pol', jeśli wcześniej było "napisy ... (google tłumacz|translator) ..."
            (?<!(?:napisy[\s._|\-]*
                   (?:google[\s._|\-]*tłumacz|translator)?
                   [\s._|\-]*))
    
            # wyjątek: nie łap 'PL|pol', jeśli wcześniej jest "napisy ... ai ..."
            (?<!(?:napisy[\s._|\-]*ai[\s._|\-]*))
    
            # NIE może być "Kinowy" tuż PRZED 'PL|pol' (z dowolnymi separatorami / nawiasami)
            (?<!kinowy[\s._\-|\]\)\(\[\}\{]*)
    
            \b(?:PL|pol)\b
    
            # NIE może być "Kinowy" tuż PO 'PL|pol' (z dowolnymi separatorami / nawiasami)
            (?![\s._\-|\]\)\(\[\}\{]*kinowy\b)
            """,
            regex.IGNORECASE | regex.VERBOSE
        ),
        uniq_concat(value("pl")),
        {"remove": True, "skipIfAlreadyFound": False}
    )



    # Networks
    parser.add_handler("network", regex.compile(r"\bATVP?\b", regex.IGNORECASE), value("Apple TV"), {"remove": True})
    parser.add_handler("network", regex.compile(r"\bAMZN\b", regex.IGNORECASE), value("Amazon"), {"remove": True})
    parser.add_handler("network", regex.compile(r"\bNF|Netflix\b", regex.IGNORECASE), value("Netflix"), {"remove": True})
    parser.add_handler("network", regex.compile(r"\bNICK(elodeon)?\b", regex.IGNORECASE), value("Nickelodeon"), {"remove": True})
    parser.add_handler("network", regex.compile(r"\bDSNY?P?\b", regex.IGNORECASE), value("Disney"), {"remove": True})
    parser.add_handler("network", regex.compile(r"\bH(MAX|BO)\b", regex.IGNORECASE), value("HBO"), {"remove": True})
    parser.add_handler("network", regex.compile(r"\bHULU\b", regex.IGNORECASE), value("Hulu"), {"remove": True})
    parser.add_handler("network", regex.compile(r"\bCBS\b", regex.IGNORECASE), value("CBS"), {"remove": True})
    parser.add_handler("network", regex.compile(r"\bNBC\b", regex.IGNORECASE), value("NBC"), {"remove": True})
    parser.add_handler("network", regex.compile(r"\bAMC\b", regex.IGNORECASE), value("AMC"), {"remove": True})
    parser.add_handler("network", regex.compile(r"\bPBS\b", regex.IGNORECASE), value("PBS"), {"remove": True})
    parser.add_handler("network", regex.compile(r"\b(Crunchyroll|[. -]CR[. -])\b", regex.IGNORECASE), value("Crunchyroll"), {"remove": True})
    parser.add_handler("network", regex.compile(r"\bVICE\b"), value("VICE"), {"remove": True})
    parser.add_handler("network", regex.compile(r"\bSony\b", regex.IGNORECASE), value("Sony"), {"remove": True})
    parser.add_handler("network", regex.compile(r"\bHallmark\b", regex.IGNORECASE), value("Hallmark"), {"remove": True})
    parser.add_handler("network", regex.compile(r"\bAdult.?Swim\b", regex.IGNORECASE), value("Adult Swim"), {"remove": True})
    parser.add_handler("network", regex.compile(r"\bAnimal.?Planet|ANPL\b", regex.IGNORECASE), value("Animal Planet"), {"remove": True})
    parser.add_handler("network", regex.compile(r"\bCartoon.?Network(.TOONAMI.BROADCAST)?\b", regex.IGNORECASE), value("Cartoon Network"), {"remove": True})

    # Extension
    parser.add_handler("extension", regex.compile(r"\.(3g2|3gp|avi|flv|mkv|mk3d|mov|mp2|mp4|m4v|mpe|mpeg|mpg|mpv|webm|wmv|ogm|divx|ts|m2ts|iso|vob|sub|idx|ttxt|txt|smi|srt|ssa|ass|vtt|nfo|html)$", regex.IGNORECASE), lowercase, {"remove": True})
    parser.add_handler("audio", regex.compile(r"\bMP3\b", regex.IGNORECASE), uniq_concat(value("MP3")), {"remove": True, "skipIfAlreadyFound": False})

    # Group
    parser.add_handler("group", regex.compile(r"\(([\w-]+)\)(?:$|\.\w{2,4}$)"))
    parser.add_handler("group", regex.compile(r"\b(INFLATE|DEFLATE)\b"), value("$1"), {"remove": True})
    parser.add_handler("group", regex.compile(r"\b(?:Erai-raws|Erai-raws\.com)\b", regex.IGNORECASE), value("Erai-raws"), {"remove": True})
    parser.add_handler("group", regex.compile(r"^\[([^[\]]+)]"))

    def handle_group_exclusion(context):
        result = context["result"]
        if "group" in result and result["group"] in ["-", ""]:
            del result["group"]
        return None

    parser.add_handler("group", handle_group_exclusion)

    parser.add_handler("trash", regex.compile(r"acesse o original", regex.IGNORECASE), boolean, {"remove": True})
    parser.add_handler("title", regex.compile(r"\bHigh.?Quality\b", regex.IGNORECASE), none, {"remove": True, "skipFromTitle": True})
    parser.add_handler("cleanup", handle_trash_after_markers)
