#!/usr/bin/python3

import http.cookiejar, requests, re, json, os, threading, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from progress_store import progress_data, progress_lock

progress_lock = threading.Lock()
url_reached: 0

class ScrapNotes:
    LANG = 'EN-GB' # ou 'FR-FR Comming soon...'
    DOMAIN = 'pitch-icam.rima1.fr'
    PATH = '/'
    COOKIE_NAME = '.DotNetCasClientAuth'

    def get_icam_cookie(self, login, mot_de_passe):
        url_cas_connexion = "https://cas.icam.fr/cas/login"
        url_portfolio = "https://pitch-icam.rima1.fr/EN-GB/MyCursus/Home"
        try:
            session = requests.Session()
            response_cas = session.get(url_cas_connexion)
            response_cas.raise_for_status()

            execution_match = re.search(r'name="execution" value="([^"]+)"', response_cas.text)
            if execution_match:
                execution_value = execution_match.group(1)
            else:
                print("Valeur du champ 'execution' non trouvée.")
                return None

            donnees_connexion = {
                'username': login,
                'password': mot_de_passe,
                'execution': execution_value,
                '_eventId': 'submit',
                'geolocation': ''
            }

            response_cas_post = session.post(url_cas_connexion, data=donnees_connexion)
            response_cas_post.raise_for_status()

            if "Connexion réussie" in response_cas_post.text:
                print("Connexion CAS réussie !")

                response_pitch = session.get(url_portfolio)
                response_pitch.raise_for_status()

                if "PITCH" in response_pitch.text:
                    print("Page Pitch Icam chargée avec succès !")
                    cookies = session.cookies.get_dict()
                    dotnet_cookie = cookies.get(self.COOKIE_NAME)
                    if dotnet_cookie:
                        return dotnet_cookie
                    else:
                        print("Cookie .DotNetCasClientAuth non trouvé.")
                        return None
                else:
                    print("Échec du chargement de la page Pitch Icam.")
                    return None
            else:
                print("Échec de la connexion CAS. Vérifiez vos identifiants ou le site web.")
                return None

        except requests.exceptions.RequestException as e:
            print(f"Erreur de requête : {e}")
            return None

    def get_json_from_icam(self, url, cookie_value, clean_username):
        cookie = http.cookiejar.Cookie(
            version=0,
            name=self.COOKIE_NAME,
            value=cookie_value,
            port=None,
            port_specified=False,
            domain=self.DOMAIN,
            domain_specified=True,
            domain_initial_dot=False,
            path=self.PATH,
            path_specified=True,
            secure=False,
            expires=None,
            discard=False,
            comment=None,
            comment_url=None,
            rest={},
            rfc2109=False,
        )

        cookies = http.cookiejar.CookieJar()
        cookies.set_cookie(cookie)
        try:
            response = requests.get(url, cookies=cookies)
            response.raise_for_status()
            if clean_username:
                with progress_lock:
                    progress_data[clean_username]["requests"] += 1
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Erreur de requête : {e}")
            return None
        except ValueError as e:
            print(f"Erreur de décodage JSON : {e}")
            return None

    def get_skill_blocks(self, cookie_value, clean_username):
        url = f"https://pitch-icam.rima1.fr/api/SkillBlock?ProgramCode=BI&VersionCode=2022&culture={self.LANG}&simpleversion=false"
        json_data = self.get_json_from_icam(url, cookie_value, clean_username)

        if not json_data:
            print("Aucune donnée SkillBlock reçue.")
            return {}

        result = {}
        for item in json_data:
            code = item.get("Code")
            if code:
                result[code] = {
                    "PctMinAcq": item.get("PctMinAcq"),
                    "Progress": item.get("Progress")
                }
        return result
        
    def get_cat_niv1(self, cookie_value, main_cat, clean_username):
        """Renvoie les catégories de niveau 1, titres, pourcentages..."""
        url = f"https://pitch-icam.rima1.fr/api/LearningGoal?BlockCode={main_cat}&Graph=Bar&ProgramCode=BI&VersionCode=2022&culture={self.LANG}"
        json_data = self.get_json_from_icam(url, cookie_value, clean_username)

        if not json_data:
            print("Aucune donnée reçue.")
            return None

        keys_to_keep = ["LGCode", "LGTitle", "MinPrgPct", "Progress"]
        infos = [{key: item.get(key) for key in keys_to_keep} for item in json_data]
        return infos
    
    def get_cat_niv2(self, cookie_value, main_cat, LGCode, clean_username):
        """Ouvre les catégories de niveau 1 pour renvoyer les catégories niv2, titres, pourcentages..."""
        url = f"https://pitch-icam.rima1.fr/api/LearningGoal?BlockCode={main_cat}&Graph=Bar&LGCode={LGCode}&ProgramCode=BI&VersionCode=2022&culture={self.LANG}"
        json_data = self.get_json_from_icam(url, cookie_value, clean_username)

        if not json_data:
            print("Aucune donnée reçue.")
            return None

        keys_to_keep = ["Code", "Title", "MinPrgPct", "Progress"]
        infos = [{key: item.get(key) for key 
                  in keys_to_keep} for item in json_data]
        return infos

    def get_cat_details(self, cookie_value, LGCode, LOCode, clean_username):
        url = f"https://pitch-icam.rima1.fr/api/locdetail?LGCode={LGCode}&LOCode={LOCode}&ParentProgramCode=BI&culture={self.LANG}"
        json_data = self.get_json_from_icam(url, cookie_value, clean_username)

        if not json_data or not isinstance(json_data, list):
            print("Données JSON inattendues :", json_data)
            return None

        result = []
        
        for trait in json_data:
            trait_code = trait.get("TraitCode")
            trait_title = trait.get("TraitTitle")

            course_details = []
            for course in trait.get("CourseList", []):
                course_info = {
                    "CourseCode": course.get("CourseCode"),
                    "Title": course.get("Title"),
                    "CourseStatus": course.get("CourseStatus"),
                    "BlockNoteEntry": course.get("BlockNoteEntry"),
                    "ProgramTitle": course.get("ProgramTitle"),
                    "GroupCode": course.get("GroupCode"),
                }
                course_details.append(course_info)

            result.append({
                "TraitCode": trait_code,
                "TraitTitle": trait_title,
                "CourseList": course_details
            })
        return result


def fetch_niv2_data(scraper, cookie_value, main_cat, category, clean_username):
    """ Récupère les sous-catégories de niveau 2 de manière parallèle """
    lg_code = category["LGCode"]
    cat_niv2 = scraper.get_cat_niv2(cookie_value, main_cat, lg_code, clean_username)
    if cat_niv2:
        with ThreadPoolExecutor(max_workers=5) as executor:
            future_to_subcategory = {
                executor.submit(scraper.get_cat_details, cookie_value, lg_code, sub_category["Code"], clean_username): sub_category
                for sub_category in cat_niv2
            }
            for future in as_completed(future_to_subcategory):
                sub_category = future_to_subcategory[future]
                try:
                    sub_category["cat_details"] = future.result() if future.result() else []
                except Exception as e:
                    print(f"Erreur lors de la récupération des détails de {sub_category['Code']}: {e}")
    category["niv2"] = cat_niv2 if cat_niv2 else []



def main(username, password, clean_username):
    scraper = ScrapNotes()
    cookie_value = scraper.get_icam_cookie(username, password)

    all_data = []

    with progress_lock:
        progress_data[clean_username]["total"] = 97
        progress_data[clean_username]["current"] = 0
        progress_data[clean_username]["requests"] = 0

    skill_blocks_data = scraper.get_skill_blocks(cookie_value, clean_username)

    main_cats = list(skill_blocks_data.keys())

    for main_cat in main_cats:
        cat_niv1 = scraper.get_cat_niv1(cookie_value, main_cat, clean_username)
        skillblock_info = skill_blocks_data.get(main_cat, {})
        if cat_niv1:
            with ThreadPoolExecutor(max_workers=5) as executor:
                futures = [executor.submit(fetch_niv2_data, scraper, cookie_value, main_cat, category, clean_username) for category in cat_niv1]
                for future in as_completed(futures):
                    category = cat_niv1[futures.index(future)]
                    future.result()
                    with progress_lock:
                        progress_data[clean_username]["current"] += 1
                        progress_data[clean_username]["skill"] = category["LGCode"]

                    print(progress_data[clean_username]["skill"])

        all_data.append({
        "main_cat": main_cat,
        "PctMinAcq": skillblock_info.get("PctMinAcq"),
        "Progress": skillblock_info.get("Progress"),
        "categories": cat_niv1 if cat_niv1 else []
    })

    file_path = f"data/{clean_username}.json"
    with open(file_path, "w", encoding="utf-8") as json_file:
        json.dump(all_data, json_file, indent=4, ensure_ascii=False)

    print(f"Fichier JSON enregistré : {file_path}")
    print(f"Nombre total de requests : {progress_data[clean_username]['requests']}")

if __name__ == "__main__":
    main()