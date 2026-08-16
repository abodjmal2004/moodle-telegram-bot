"""
MoodleClient - Fixed Extended Version
(Login + Courses + Grades + Assignments + Announcements + Content + Deadlines)
"""
import asyncio
import logging
import re
from typing import Optional, List, Dict

import aiohttp
from bs4 import BeautifulSoup
from cachetools import TTLCache

logger = logging.getLogger(__name__)

BASE_URL = "https://moodle.alaqsa.edu.ps"

MAX_RETRIES = 3  # عدد محاولات إعادة الطلب قبل الاستسلام (شبكة/timeout)

COMMON_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 15; Pixel 9) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/150.0.0.0 Mobile Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,"
              "image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "ar;q=0.6",
    "Cache-Control": "max-age=0",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Ch-Ua": '"Not;A=Brand";v="8", "Chromium";v="150", "Brave";v="150"',
    "Sec-Ch-Ua-Mobile": "?1",
    "Sec-Ch-Ua-Platform": '"Android"',
    "Sec-Gpc": "1",
}

ASSIGN_RE = re.compile(r"/mod/assign/view\.php\?id=(\d+)")
MOD_ID_RE = re.compile(r"[?&]id=(\d+)")


class MoodleClient:
    def __init__(self) -> None:
        self._session: Optional[aiohttp.ClientSession] = None
        self._username: Optional[str] = None
        self._password: Optional[str] = None
        self._is_logged_in: bool = False
        self._sesskey: Optional[str] = None
        # كاش قصير الأمد (بالذاكرة) لصفحات Moodle الأكثر طلباً — بيقلل
        # عدد الطلبات لموقع الجامعة كتير لما المستخدم يتنقل بين نفس
        # الشاشات، وبيخلي الاستجابة فورية بدل انتظار scraping من جديد.
        # TTL قصير (120 ثانية) عشان البيانات (درجات، واجبات جديدة) ما
        # تضل قديمة كتير.
        self._cache = TTLCache(maxsize=64, ttl=120)

    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers=COMMON_HEADERS,
                cookie_jar=aiohttp.CookieJar(unsafe=False),
            )
            self._is_logged_in = False
            self._sesskey = None
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
        self._session = None
        self._is_logged_in = False
        self._sesskey = None

    async def get_full_name(self) -> Optional[str]:
        """يجيب الاسم الكامل (الرسمي) من صفحة البروفايل الشخصي، بدل الاسم
        القصير يلي بيطلع من /my/.

        الصيغة الفعلية لـ <title> بموقع الجامعة (تأكدت منها من الـ HTML
        الحقيقي):
            "الاسم الكامل: ملف شخصي علني | بوابة التعليم الإلكتروني- ..."
        يعني الاسم قبل أول ":" مش بعده. هاي المحاولة الأساسية، وباقي
        المحاولات احتياطية بس لو تغيرت الصيغة مستقبلاً."""
        html = await self._fetch_url("/user/profile.php")
        if not html:
            return None

        soup = BeautifulSoup(html, "html.parser")

        # محاولة 1 (الأساسية، مؤكدة من الـ HTML الحقيقي):
        # <title>الاسم: ملف شخصي علني | ...</title>
        if soup.title:
            title_text = soup.title.get_text(strip=True)
            if ":" in title_text:
                candidate = title_text.split(":", 1)[0].strip()
                if candidate and len(candidate) > 1:
                    return candidate

        # محاولة 2: عنوان الصفحة الرئيسي (احتياطي لو الـ theme تغير)
        header = soup.find("div", class_=lambda c: c and "page-header-headings" in str(c))
        if header:
            h = header.find(["h1", "h2"])
            name = h.get_text(strip=True) if h else header.get_text(strip=True)
            if name and len(name) > 1:
                return name

        # محاولة 3: أول h1 بالصفحة
        h1 = soup.find("h1")
        if h1:
            name = h1.get_text(strip=True)
            if name and len(name) > 1:
                return name

        # محاولة 4: meta og:title
        meta = soup.find("meta", attrs={"property": "og:title"})
        if meta and meta.get("content"):
            name = meta["content"].strip()
            if ":" in name:
                name = name.split(":", 1)[0].strip()
            if name and len(name) > 1:
                return name

        return None

    async def login(self, username: str, password: str) -> dict:
        self._username = username
        self._password = password
        session = await self._ensure_session()
        try:
            async with session.get(
                f"{BASE_URL}/login/index.php",
                headers={**COMMON_HEADERS, "Sec-Fetch-Site": "none", "Sec-Fetch-User": "?1"},
                ssl=True, timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                html = await resp.text()
        except Exception as e:
            return {"success": False, "message": f"خطأ في الاتصال: {str(e)}", "user_name": None}

        token = self._extract_logintoken(html)
        if not token:
            return {"success": False, "message": "ما لقيتش logintoken", "user_name": None}

        try:
            async with session.post(
                f"{BASE_URL}/login/index.php",
                data={"anchor": "", "logintoken": token, "username": username, "password": password},
                headers={**COMMON_HEADERS, "Origin": BASE_URL,
                         "Referer": f"{BASE_URL}/login/index.php",
                         "Content-Type": "application/x-www-form-urlencoded",
                         "Sec-Fetch-Site": "same-origin", "Sec-Fetch-User": "?1"},
                ssl=True, timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                final_html = await resp.text()
                final_url = str(resp.url)
        except Exception as e:
            return {"success": False, "message": f"خطأ في الاتصال: {str(e)}", "user_name": None}

        is_ok, user_name = self._verify_login(final_html, final_url)
        self._is_logged_in = is_ok
        if is_ok:
            self._sesskey = self._extract_sesskey(final_html)

        full_name = None
        if is_ok:
            try:
                full_name = await self.get_full_name()
            except Exception as e:
                logger.debug("get_full_name failed: %s", e)

        if is_ok:
            display_name = full_name or user_name or "مستخدم"
            return {
                "success": True, "message": f"أهلاً {display_name}!",
                "user_name": user_name, "full_name": full_name,
            }
        return {"success": False, "message": "اسم المستخدم أو كلمة المرور غير صحيحة.",
                "user_name": None, "full_name": None}

    @staticmethod
    def _extract_logintoken(html: str) -> Optional[str]:
        soup = BeautifulSoup(html, "html.parser")
        inp = soup.find("input", {"name": "logintoken"})
        if inp:
            return inp.get("value")
        m = re.search(r'<input[^>]*name="logintoken"[^>]*value="([^"]*)"', html)
        return m.group(1) if m else None

    @staticmethod
    def _extract_sesskey(html: str) -> Optional[str]:
        m = re.search(r'"sesskey"\s*:\s*"([a-zA-Z0-9]+)"', html)
        if m:
            return m.group(1)
        soup = BeautifulSoup(html, "html.parser")
        inp = soup.find("input", {"name": "sesskey"})
        if inp:
            return inp.get("value")
        logout = soup.find("a", href=re.compile(r"login/logout\.php\?sesskey="))
        if logout:
            m = re.search(r"sesskey=([a-zA-Z0-9]+)", logout["href"])
            if m:
                return m.group(1)
        m = re.search(r"sesskey[=:]\s*['\"]?([a-zA-Z0-9]{8,20})['\"]?", html)
        if m:
            return m.group(1)
        return None

    @staticmethod
    def _verify_login(html: str, url: str) -> tuple:
        soup = BeautifulSoup(html, "html.parser")
        for el in soup.find_all(class_=True):
            cls = " ".join(el.get("class", []))
            if "loginerrors" in cls or ("alert" in cls and "danger" in cls):
                return False, None
        if "loginerrors" in html or "Invalid login" in html:
            return False, None
        if "login/logout.php" in html or "/my" in url:
            user_elem = soup.find("span", class_="usertext")
            return True, user_elem.get_text(strip=True) if user_elem else None
        return False, None

    async def health_check(self) -> dict:
        """فحص صحة الاتصال والجلسة مع موقع مودل — بيرجع تقرير شامل:
        * connection: هل السيرفر بيجاوب (GET صفحة الدخول < 15s)
        * logged_in: هل جلسة المستخدم الحالية لسا صالحة
        * moodle_up: هل موقع الجامعة شغال بالكامل (بدون أي اعتبار لجلستك)

        مودل بيغلق الجلسات بعد ~ساعتين من عدم النشاط، وده أشيع سبب
        لفشل الأوامر للمستخدمين القدامى — الفحص بيقولك بالضبط وين المشكلة."""
        report = {"moodle_up": False, "connection": False, "logged_in": False}
        session = await self._ensure_session()
        # 1) هل السيرفر بيجاوب من الأساس؟
        try:
            async with session.get(
                f"{BASE_URL}/login/index.php", headers=COMMON_HEADERS,
                ssl=True, timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                html = await resp.text()
                report["connection"] = True
                report["moodle_up"] = "logintoken" in html or resp.status < 500
        except Exception:
            pass
        # 2) هل جلسة المستخدم لسا صالحة؟
        if report["connection"]:
            report["logged_in"] = await self._ensure_logged_in()
        return report

    async def _ensure_logged_in(self) -> bool:
        if self._is_logged_in and self._session and not self._session.closed:
            try:
                async with self._session.get(
                    f"{BASE_URL}/my/", timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    html = await resp.text()
                    if "login/logout.php" in html:
                        self._sesskey = self._extract_sesskey(html) or self._sesskey
                        return True
            except Exception:
                pass
        if self._username and self._password:
            result = await self.login(self._username, self._password)
            return result["success"]
        return False

    async def _fetch_url(self, path: str, retries: int = MAX_RETRIES) -> Optional[str]:
        """GET بـ retry — لو انقطع الاتصال أو الـ timeout انقطع، بيحاول
        كذا مرة (backoff متزايد) قبل ما يستسلم. الشبكات الجامعية معروفة
        بقلة الاستقرار فهاد بقلل حالات «ما قدرتش أجيب الصفحة» كتير."""
        session = await self._ensure_session()
        last_error = None
        for attempt in range(retries):
            try:
                async with session.get(
                    f"{BASE_URL}{path}",
                    headers={**COMMON_HEADERS, "Sec-Fetch-Site": "same-origin", "Sec-Fetch-User": "?1"},
                    ssl=True, timeout=aiohttp.ClientTimeout(total=30),
                ) as resp:
                    if resp.status >= 400:
                        return None
                    return await resp.text()
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                last_error = e
                await asyncio.sleep(1.5 * (attempt + 1))
        if last_error:
            logger.debug("fetch failed after %d retries (%s): %s", retries, path, last_error)
        return None

    async def _ajax_call(self, method: str, args: dict) -> Optional[Dict]:
        if not self._sesskey:
            return None
        payload = [{"index": 0, "methodname": method, "args": args}]
        session = await self._ensure_session()
        last_error = None
        for attempt in range(MAX_RETRIES):
            try:
                async with session.post(
                    f"{BASE_URL}/lib/ajax/service.php?sesskey={self._sesskey}",
                    json=payload,
                    headers={**COMMON_HEADERS,
                             "Accept": "application/json, text/javascript, */*; q=0.01",
                             "Content-Type": "application/json",
                             "X-Requested-With": "XMLHttpRequest",
                             "Referer": BASE_URL + "/my/"},
                    ssl=True, timeout=aiohttp.ClientTimeout(total=30),
                ) as resp:
                    data = await resp.json(content_type=None)
                    break
            except Exception as e:
                last_error = e
                await asyncio.sleep(1.5 * (attempt + 1))
        else:
            if last_error:
                logger.debug("ajax call failed after %d retries: %s", MAX_RETRIES, last_error)
            return None
        if not isinstance(data, list) or not data:
            return None
        item = data[0]
        if item.get("error"):
            err = item.get("exception", {}).get("errorcode", "")
            if err == "servicerequireslogin":
                self._is_logged_in = False
            logger.debug("ajax error: %s", err)
            return None
        return item.get("data")

    async def get_courses(self) -> List[Dict]:
        if not await self._ensure_logged_in():
            raise RuntimeError("Not logged in")

        cache_key = ("courses",)
        if cache_key in self._cache:
            return self._cache[cache_key]

        html = await self._fetch_url("/my/courses.php") or await self._fetch_url("/my/")
        if not html:
            raise RuntimeError("ما قدرتش أجيب صفحة المواد")
        fresh = self._extract_sesskey(html)
        if fresh:
            self._sesskey = fresh

        if self._sesskey:
            courses = await self._ajax_call(
                "core_course_get_enrolled_courses_by_timeline_classification",
                {"classification": "all", "sort": "fullname", "limit": 50, "offset": 0})
            if courses and "courses" in courses:
                result = [{"id": str(c["id"]), "name": c.get("fullname") or c.get("shortname", ""),
                           "url": f"{BASE_URL}/course/view.php?id={c['id']}"}
                          for c in courses["courses"]]
                if result:
                    self._cache[cache_key] = result
                return result

        logger.debug("AJAX failed, trying HTML parse...")
        result = self._parse_courses_from_html(html)
        if result:
            self._cache[cache_key] = result
        return result

    def _parse_courses_from_html(self, html: str) -> List[Dict]:
        soup = BeautifulSoup(html, "html.parser")
        courses: Dict[str, Dict] = {}

        def try_add(cid, name, url):
            if cid and name and len(name) > 1 and cid not in courses:
                courses[cid] = {"id": cid, "name": name, "url": url}

        for elem in soup.find_all(attrs={"data-course-id": True}):
            cid = elem.get("data-course-id")
            if cid and cid.isdigit():
                name = elem.get("aria-label") or elem.get("title") or elem.get_text(strip=True)
                if name and len(name) > 2:
                    try_add(cid, name, f"{BASE_URL}/course/view.php?id={cid}")
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "course/view.php?id=" not in href or "category" in href:
                continue
            m = MOD_ID_RE.search(href)
            cid = m.group(1) if m else None
            name = a.get_text(strip=True) or a.get("title") or ""
            if cid and name and len(name) > 2:
                try_add(cid, name, href)
        return list(courses.values())

    async def get_course_content(self, course_id: int) -> List[Dict]:
        if not await self._ensure_logged_in():
            raise RuntimeError("Not logged in")

        data = await self._ajax_call("core_course_get_contents", {"courseid": course_id})
        if data and isinstance(data, list) and data:
            items = []
            for section in data:
                section_name = section.get("name") or f"قسم {section.get('section', '?')}"
                for mod in section.get("modules", []):
                    items.append({
                        "section": section_name,
                        "type": mod.get("modname", ""),
                        "name": mod.get("name", ""),
                        "url": mod.get("url", ""),
                        "completion": mod.get("completiondata", {}).get("state", None),
                    })
            if items:
                return items

        logger.debug("AJAX contents failed, trying HTML parse...")
        html = await self._fetch_url(f"/course/view.php?id={course_id}")
        if not html:
            return []
        return self._parse_course_content_html(html)

    def _parse_course_content_html(self, html: str) -> List[Dict]:
        soup = BeautifulSoup(html, "html.parser")
        items = []
        # البحث عن الأقسام: ممكن تكون li أو section حسب الثيم (Boost/Classic)
        sections = soup.find_all(["li", "section", "div"], attrs={"id": re.compile(r"^section-")})
        for sec in sections:
            # استخراج اسم القسم
            sec_name_elem = sec.find(["h3", "h4", "span"], class_=lambda c: c and ("sectionname" in str(c) or "section-title" in str(c)))
            if sec_name_elem:
                sec_name = sec_name_elem.get_text(strip=True)
            else:
                sec_id_m = re.search(r"section-(\d+)", sec.get("id", ""))
                sec_name = f"قسم {sec_id_m.group(1)}" if sec_id_m else "قسم"

            # البحث عن الأنشطة داخل القسم
            activities = sec.find_all(["li", "div"], class_=lambda c: c and ("activity" in str(c)))
            for act in activities:
                link = act.find("a", href=True)
                if not link:
                    continue
                
                # استخراج النوع من الكلاس (modtype_assign, modtype_resource, etc.)
                modname = None
                classes = act.get("class", [])
                if isinstance(classes, list):
                    for c in classes:
                        if c.startswith("modtype_"):
                            modname = c.replace("modtype_", "")
                            break
                
                # لو ما لقينا الكلاس، نجرب نبحث عن الأيقونة أو الرابط
                if not modname:
                    if "assign" in link["href"]: modname = "assign"
                    elif "forum" in link["href"]: modname = "forum"
                    elif "resource" in link["href"]: modname = "resource"
                    elif "quiz" in link["href"]: modname = "quiz"

                # استخراج الاسم - أحياناً يكون داخل سبان مع نص إضافي (Hidden, etc)
                name_elem = act.find("span", class_="instancename")
                if name_elem:
                    # نأخذ النص الأول فقط (الاسم الفعلي) ونتجاهل الـ span اللي فيه نوع النشاط
                    name = name_elem.find(string=True, recursive=False) or name_elem.get_text(strip=True)
                else:
                    name = link.get_text(strip=True)
                
                # تنظيف الاسم من الكلمات الزائدة (Activity name, etc)
                if name:
                    name = re.sub(r"^(Assignment|Task|File|URL|Forum|Quiz|Page|Folder|Book)\s*", "", name, flags=re.I)
                    items.append({
                        "section": sec_name, 
                        "type": modname or "",
                        "name": name.strip(), 
                        "url": link["href"], 
                        "completion": None
                    })
        return items

    async def get_announcements(self, course_id: int) -> List[Dict]:
        if not await self._ensure_logged_in():
            raise RuntimeError("Not logged in")

        cache_key = ("announcements", course_id)
        if cache_key in self._cache:
            return self._cache[cache_key]

        html = await self._fetch_url(f"/course/view.php?id={course_id}")
        if not html:
            return []

        soup = BeautifulSoup(html, "html.parser")
        news_link = None

        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "mod/forum/view" in href:
                title = (a.get("title", "") or a.get_text(strip=True) or "").lower()
                if any(k in title for k in ["أخبار", "اخبار", "news", "announcement", "إعلان"]):
                    news_link = href
                    break

        if not news_link:
            m = re.search(r'href="([^"]*mod/forum/view[^"]*)"', html)
            if m:
                news_link = m.group(1)

        if not news_link:
            return []

        news_html = await self._fetch_url("/" + news_link.split(BASE_URL, 1)[-1].lstrip("/"))
        if not news_html:
            return []
        result = self._parse_forum_posts(news_html)
        if result:
            self._cache[cache_key] = result
        return result

    def _parse_forum_posts(self, html: str) -> List[Dict]:
        soup = BeautifulSoup(html, "html.parser")
        posts = []
        seen = set()

        # البحث في div (Boost) أو tr (Classic)
        items = soup.find_all(["div", "tr"], class_=lambda c: c and ("discussion" in str(c) or "discussion-list-item" in str(c)))
        for entry in items:
            title_a = entry.find("a", href=True)
            if not title_a or "discuss.php" not in title_a["href"]:
                continue
            
            key = title_a["href"]
            if key in seen:
                continue
            seen.add(key)
            
            author = ""
            # البحث عن المؤلف في كلاسات متنوعة
            author_elem = entry.find(class_=lambda c: c and ("author" in str(c) or "user" in str(c)))
            if author_elem:
                author = author_elem.get_text(strip=True)
            
            time_str = ""
            # البحث عن الوقت
            time_elem = entry.find(class_=lambda c: c and ("time" in str(c) or "lastpost" in str(c) or "timestart" in str(c)))
            if time_elem:
                time_str = time_elem.get_text(strip=True)
            
            posts.append({
                "title": title_a.get_text(strip=True),
                "url": title_a["href"],
                "author": author,
                "time": time_str,
            })

        return posts

    async def get_assignments(self, course_id: int) -> List[Dict]:
        if not await self._ensure_logged_in():
            raise RuntimeError("Not logged in")

        cache_key = ("assignments", course_id)
        if cache_key in self._cache:
            return self._cache[cache_key]

        data = await self._ajax_call("mod_assign_get_assignments", {"courseids": [course_id]})
        if data and isinstance(data, dict) and "courses" in data:
            out = []
            for course in data.get("courses", []):
                for a in course.get("assignments", []):
                    status = None
                    if a.get("status"):
                        status = "تم التسليم" if a["status"] == "submitted" else "لم يتم التسليم"
                    out.append({
                        "course_id": course_id,
                        "assignment_id": a.get("id"),
                        "name": a.get("name", ""),
                        "due_date": a.get("duedate"),
                        "due_date_text": a.get("formattedduedate", ""),
                        "status": status,
                        "url": f"{BASE_URL}/mod/assign/view.php?id={a.get('cmid')}",
                    })
            if out:
                self._cache[cache_key] = out
                return out

        logger.debug("AJAX assignments empty, trying HTML parse...")
        html = await self._fetch_url(f"/course/view.php?id={course_id}")
        if not html:
            return []
        result = self._parse_assignments_html(html, course_id)
        if result:
            self._cache[cache_key] = result
        return result

    def _parse_assignments_html(self, html: str, course_id: int) -> List[Dict]:
        soup = BeautifulSoup(html, "html.parser")
        assignments = []
        selectors = [
            soup.find_all("li", class_=lambda x: x and "modtype_assign" in str(x)),
            soup.find_all("div", class_=lambda x: x and "modtype_assign" in str(x)),
        ]
        for activities in selectors:
            for activity in activities:
                link = activity.find("a", href=True)
                if not link:
                    continue
                m = ASSIGN_RE.search(link["href"])
                if not m:
                    continue
                name = link.get_text(strip=True)
                due = None
                info = activity.find("div", class_=lambda x: x and "info" in str(x))
                if info:
                    t = info.get_text(strip=True)
                    if "تسليم" in t or "Due" in t:
                        due = t
                status = None
                txt = activity.get_text()
                if "تم التسليم" in txt or "Submitted" in txt:
                    status = "تم التسليم"
                elif "لم يتم التسليم" in txt or "Not submitted" in txt:
                    status = "لم يتم التسليم"
                assignments.append({
                    "course_id": course_id, "assignment_id": m.group(1), "name": name,
                    "due_date": due, "due_date_text": due, "status": status,
                    "url": link["href"],
                })
            if assignments:
                break
        return assignments

    async def get_upcoming_deadlines(self) -> List[Dict]:
        if not await self._ensure_logged_in():
            raise RuntimeError("Not logged in")

        data = await self._ajax_call("core_calendar_get_calendar_upcoming_events", {})
        items = []
        if data and isinstance(data, dict):
            events = data.get("events", [])
            for ev in events:
                items.append({
                    "title": ev.get("name", ""),
                    "course": ev.get("course", {}).get("fullname", ""),
                    "course_id": ev.get("course", {}).get("id"),
                    "time": ev.get("formattedtime") or ev.get("timestart"),
                    "type": ev.get("eventtype", ""),
                    "url": ev.get("url", ""),
                })
            if items:
                return items

        html = await self._fetch_url("/calendar/view.php?view=upcoming")
        if html:
            soup = BeautifulSoup(html, "html.parser")
            for row in soup.find_all("div", class_=lambda c: c and "event" in str(c)):
                title_a = row.find("a", href=True)
                title = title_a.get_text(strip=True) if title_a else row.get_text(strip=True)[:100]
                if title:
                    items.append({"title": title, "course": "", "course_id": None,
                                  "time": "", "type": "",
                                  "url": title_a["href"] if title_a else ""})
        return items

    async def get_grades(self, course_id: Optional[int] = None) -> List[Dict]:
        if not await self._ensure_logged_in():
            raise RuntimeError("Not logged in")
        session = await self._ensure_session()
        params = {"courseid": course_id} if course_id else {}
        async with session.get(
            f"{BASE_URL}/grade/report/user/index.php", params=params,
            headers={**COMMON_HEADERS, "Referer": f"{BASE_URL}/my/",
                     "Sec-Fetch-Site": "same-origin", "Sec-Fetch-User": "?1"},
            ssl=True, timeout=aiohttp.ClientTimeout(total=30),
        ) as resp:
            html = await resp.text()
        soup = BeautifulSoup(html, "html.parser")
        grades = []
        for table in soup.find_all("table", class_=lambda x: x and ("user-grades" in str(x) or "generaltable" in str(x))):
            for row in table.find_all("tr"):
                cells = row.find_all(["th", "td"])
                texts = [c.get_text(" ", strip=True) for c in cells]
                if len(texts) >= 2:
                    item = texts[0]
                    if item and item != "عنصر الدرجة":
                        grades.append({
                            "item": item, "grade": texts[1],
                            "range": texts[2] if len(texts) > 2 else None,
                            "percentage": texts[3] if len(texts) > 3 else None,
                        })
        return grades

    async def logout(self) -> dict:
        session = await self._ensure_session()
        try:
            logout_url = f"{BASE_URL}/login/logout.php"
            if self._sesskey:
                logout_url += f"?sesskey={self._sesskey}"
            async with session.get(
                logout_url,
                headers={**COMMON_HEADERS, "Sec-Fetch-Site": "same-origin"},
                ssl=True, timeout=aiohttp.ClientTimeout(total=10),
            ):
                pass
        except Exception:
            pass
        finally:
            await self.close()
        self._is_logged_in = False
        self._username = None
        self._password = None
        self._sesskey = None
        return {"success": True, "message": "تم تسجيل الخروج"}