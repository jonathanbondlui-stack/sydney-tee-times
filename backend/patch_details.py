"""Run: python backend/patch_details.py   Adds researched details for courses and any missing courses. Safe to re-run.

source="club" means the club, council or a booking page the club uses said it.
source="directory" means third-party listings, which the site tells people to confirm.
Directory green fees are left out on purpose: the listings disagree and many are years old.
"""
import json, os, shutil
R = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
P = lambda *a: os.path.join(R, *a)
CHECKED = "2026-11-03"
GOLFNOW = "Book on GolfNow"
GN_NOTE = "Listed on GolfNow, which may not always show times. Prices can differ from the club's, so check when you book."

def miclub(host):
    return dict(status="online", platform="miclub", host=host, resource_id=3000000, enabled=True)

UPDATES = {
 # Live times
 "stonecutters-ridge": dict(miclub("stonecutters.miclub.com.au"), source="club", note=None),
 "strathfield": dict(miclub("www.strathfieldgolf.com.au"), source="club", phone="(02) 9642 0326", address="52 Weeroona Rd, Strathfield", holes=18,
     website="https://www.strathfieldgolf.com.au/", note="Non-members can play every day except Saturday, after the morning competitions finish."),
 "georges-river": dict(suburb="Georges Hall", lat=-33.91, lon=150.985, phone="(02) 9724 1615", address="255 Henry Lawson Dr, Georges Hall", website="https://georgesrivergolf.com.au/",
     source="club", note="The club's own Book button uses TeeItUp, and its listed fees differ slightly from the MiClub page these times come from."),
 # Book online elsewhere
 "lane-cove": dict(address="180 River Rd, Lane Cove", holes=9, source="directory",
     note="Books online through Quick18. Times aren't shown here yet, so this opens their tee sheet for the day you've selected."),
 "bardwell-valley": dict(status="online", cta=GOLFNOW, book_url="https://www.golfnow.com.au/tee-times/facility/16578-bardwell-valley-golf-club/search#date={gn_date}",
     suburb="Bardwell Valley", phone="(02) 9567 7600", address="2A Hillcrest Ave, Bardwell Valley", holes=18, source="directory",
     note="Public course. This opens GolfNow for the day you've selected. Times aren't shown here yet."),
 "marrickville": dict(status="online", source="directory", note="Books through TeeItUp and GolfNow. Times aren't shown here yet."),
 "palm-beach": dict(status="online", cta=GOLFNOW, book_url="https://www.golfnow.com.au/courses/-6025-palm-beach-golf-club-dev-details",
     phone="(02) 9974 4079", address="2 Beach Rd, Palm Beach", holes=9, source="directory", note="Nine-hole public course. " + GN_NOTE),
 "dunheved": dict(status="online", cta=GOLFNOW, book_url="https://www.golfnow.com.au/courses/-4752-dunheved-golf-club-details",
     phone="(02) 9623 0239", address="176 Links Rd, St Marys", holes=18, source="directory", note=GN_NOTE),
 "lakeside-camden": dict(status="online", cta=GOLFNOW, book_url="https://www.golfnow.com.au/courses/-5052-lakeside-golf-club-at-camden-details",
     source="directory", note=GN_NOTE + " We couldn't confirm the club's phone number."),
 "barnwell-park": dict(status="online", cta=GOLFNOW, book_url="https://www.golfnow.com.au/courses/-8380-barnwell-park-golf-club-details", suburb="Five Dock",
     phone="(02) 9713 1162", address="551 Lyons Rd West, Five Dock", website="https://www.canadabay.nsw.gov.au/community/community-services/golf-courses",
     source="club", note="Council lists this number. " + GN_NOTE),
 "leonay": dict(status="online", cta=GOLFNOW, book_url="https://www.golfnow.com.au/courses/-4775-leonay-golf-club-details",
     phone="(02) 4735 5300", address="1 Leonay Pde, Leonay", holes=18, source="directory", note=GN_NOTE),
 "penrith": dict(status="online", cta=GOLFNOW, book_url="https://www.golfnow.com/courses/-5069-penrith-golf-club-details",
     address="1939 The Northern Rd, Penrith", source="directory", note=GN_NOTE + " We couldn't confirm the club's phone number."),
 "macarthur-grange": dict(status="online", cta=GOLFNOW, book_url="https://www.golfnow.com/courses/-5003-macarthur-grange-golf-course-details", suburb="Varroville",
     address="Lot 18 Raby Rd, Varroville", holes=18, source="directory", note=GN_NOTE + " We couldn't confirm the club's phone number."),
 # Visitors at set times
 "st-michaels": dict(status="set_times", phone="(02) 9326 8000", address="Jennifer St, Little Bay", website="https://www.stmichaelsgolfclub.com.au/", source="club",
     cta="Visitor information", book_url="https://www.stmichaelsgolfclub.com.au/visitors", email="golfbookings@stmichaelsgolf.com.au",
     note="No online booking. Visitors are welcome 7 days during the hours below. Times open 8 days ahead at 4pm: call the Golf Shop (ext 1) or email. No handicap needed for social play.",
     visitor_hours={"Summer": ["6am–7pm", "10am–7pm", "7am–7pm", "3pm–7pm", "7am–7pm", "3pm–7pm", "12pm–7pm"],
                    "Winter": ["9am–6pm", "10am–6pm", "7am–6pm", "3pm–6pm", "7am–6pm", "3pm–6pm", "12pm–6pm"]}),
 "the-lakes": dict(status="set_times", source="directory"),
 # Call to book
 "richmond": dict(status="phone", phone="(02) 4578 1739", address="34 Bourke St, Richmond", website="https://www.richmondgolfclub.com.au/", source="directory", note="Directories say visitors are welcome every day."),
 "canterbury": dict(status="phone", phone="(02) 9759 5444", address="Moorefields Rd, Beverly Hills", holes=9, source="club", cta="Council course page", book_url="https://www.cbcity.nsw.gov.au/canterbury-golf-course",
     note="Nine-hole council course. Open 7 days and visitors are welcome."),
 "avalon": dict(status="phone", phone="(02) 9918 2606", address="32 Old Barrenjoey Rd, Avalon", holes=9, website="https://www.northernbeaches.nsw.gov.au/things-to-do/recreation-area/avalon-golf-course", source="directory", note="Nine-hole public course on council land."),
 "glenmore-heritage-valley": dict(status="phone", phone="(02) 4733 1230", address="690 Mulgoa Rd, Mulgoa", email="golf@glenmoregolf.com.au", source="club", cta="Visitor booking information", book_url="https://glenmoregolf.com.au/glenmoregolf/php/golf/bookings.php",
     note="Social golfers are welcome. Call the pro shop (option 1) or email to book."),
 "fox-hills": dict(status="phone", suburb="Prospect", phone="(02) 9631 3390", address="55 Fox Hills Cres, Prospect", holes=18, source="directory", note="Directories say visitors are welcome every day and booking ahead is essential."),
 "randwick": dict(status="phone", website="https://randwickgolfclub.com.au/", source="directory", note="Directories say visitor times run 7 days. They disagree on the phone number, so check the club's website."),
 "camden": dict(status="phone", phone="(02) 4646 1203", address="50 Lodges Rd, Narellan", email="camden@camdengolfclub.com.au", website="https://camdengolfclub.com.au/", source="directory", note="Visitors are welcome. Contact the club to arrange a time."),
 "lynwood": dict(status="phone", phone="(02) 4580 2800", address="4 Pitt Town Bottoms Rd, Pitt Town", website="https://lynwoodcc.com.au/", source="directory", note="Public bookings are available."),
 "grose-river": dict(status="phone", phone="(02) 4572 1182", address="Nutmans Rd, Grose Wold", holes=9, source="directory", note="Nine-hole public course."),
 "woodville": dict(status="phone", phone="(02) 9632 3582", address="118 Rawson Rd, Guildford", source="club", cta="Council course page", book_url="https://www.cumberland.nsw.gov.au/woodville-public-golf-course", note="Council-run. Call the pro shop for bookings."),
 "fairfield-city": dict(status="phone", phone="(02) 9604 4007", address="Cnr Smithfield Rd and Beavors St, Prairiewood", source="directory", note="Council-run public course."),
 "hurstville": dict(status="phone", suburb="Peakhurst", phone="(02) 9534 5024", address="Lorraine St, Peakhurst", source="club", note="Council-run. See the course website to book."),
 # No booking needed
 "bondi-golf": dict(status="walkup", phone="(02) 9130 3170", address="5 Military Rd, North Bondi", holes=9, source="directory", note="Nine holes. The club has said tee times aren't required, so turn up and wait your turn. Call first, as one guide says visitor play can be restricted."),
 "botany": dict(status="walkup", source="club"),
 "pittwater-golf-centre": dict(status="walkup", source="directory", note="Driving range and mini golf rather than a full course. Listings say open daily 8am–9pm, and disagree on the phone number."),
 # Check before you go
 "parramatta": dict(status="check", phone="(02) 9635 6781", address="Park Pde, Parramatta", holes=9, source="directory", note="One directory says this course has permanently closed, while another still lists it. Call before you go."),
 "wallacia": dict(status="check", phone="(02) 4773 8417", address="13 Park Rd, Wallacia", source="directory", note="A plan reported in 2021 would cut this to nine holes for cemetery use. We couldn't confirm what is open now, so call first."),
 "hawkesbury-waters": dict(status="check", source="directory", note="We couldn't confirm this course exists under this name."),
 # Details still missing
 "colonial": dict(holes=9, source="directory", note="Nine-hole course. We couldn't find a phone number or booking method."),
 "sylvania-par3": dict(suburb="Sylvania Waters", phone="(02) 9540 1669", address="223B Belgrave Esp, Sylvania Waters", holes=9, website="https://sylvaniapar3golf.com.au/", email="enquiries@sylvaniapar3golf.com.au", source="directory", note="Nine-hole par 3. Call or email for hours and prices."),
 "auburn": dict(address="Weymouth Ave, Auburn", source="club", cta="Council course page", book_url="https://www.cumberland.nsw.gov.au/auburn-golf-course-rosnay", note="Council-run, also called Rosnay. See the council page for bookings."),
}

def new(id, name, suburb, lat, lon, status="contact", **k):
    return dict(id=id, name=name, suburb=suburb, lat=lat, lon=lon, status=status, platform=k.pop("platform", "none"), enabled=k.pop("enabled", False), coords_approx=True, **k)

NEW = [
 # Live times
 new("bayview", "Bayview Golf Club", "Mona Vale", -33.66, 151.30, status="online", platform="miclub", enabled=True, host="miclubrd18.miclub.com.au", resource_id=3000000,
     phone="(02) 9999 3078", address="1825 Pittwater Rd, Mona Vale", source="club"),
 new("riverside-oaks", "Riverside Oaks Golf Resort", "Cattai", -33.54, 150.92, status="online", platform="miclub", enabled=True, host="riversideoaks.miclub.com.au", resource_id=3000000,
     phone="(02) 4560 3200", address="74 O'Briens Rd, Cattai", source="directory"),
 # Call to book
 new("ryde-parramatta", "Ryde-Parramatta Golf Club", "West Ryde", -33.80, 151.08, status="phone", address="1156 Victoria Rd, West Ryde", email="golf@rydeparramatta.com.au", website="https://rydeparramatta.com.au/", source="directory", note="Directories say visitors are welcome and booking is essential. They disagree on the phone number."),
 new("liverpool", "Liverpool Golf Club", "Lansvale", -33.905, 150.97, status="phone", phone="(02) 9728 7777", address="Hollywood Dr, Lansvale", source="directory", note="Pro shop: (02) 9727 2422."),
 new("kogarah", "Kogarah Golf Club", "Arncliffe", -33.94, 151.16, status="phone", phone="(02) 9567 0334", address="Marsh St, Arncliffe", source="directory", note="Directories say visitors are welcome daily."),
 new("castle-hill", "Castle Hill Country Club", "Baulkham Hills", -33.76, 151.00, status="phone", phone="(02) 9634 2573", address="Spurway Dr, Baulkham Hills", source="directory", note="One directory says visitors are welcome every day."),
 # Limited visitor access
 new("concord", "Concord Golf Club", "Concord", -33.85, 151.10, status="enquiry", phone="(02) 9743 6111", address="Majors Bay Rd, Concord", cta="Visitor tee times", book_url="https://play.concordgolfclub.com.au/", source="club", note="Private club. Interstate and international visitors who belong to a recognised club can view and request times, as can reciprocal club members."),
 new("monash", "Monash Country Club", "Ingleside", -33.68, 151.26, status="enquiry", phone="(02) 9913 8282", website="https://monashcc.com.au/", email="golf@monashcc.com.au", source="directory", note="Private club. Limited unaccompanied visitor play on Mon, Tue and Thu for members of other golf clubs. Handicap required and book ahead."),
 new("nsw-golf", "New South Wales Golf Club", "La Perouse", -33.99, 151.24, status="enquiry", phone="(02) 9661 4455", website="https://www.nswgolfclub.com.au/", source="club", note="Private club. Limited unaccompanied weekday access, only for people living outside NSW."),
 # Members and guests
 new("manly", "Manly Golf Club", "Balgowlah", -33.79, 151.28, status="members", phone="(02) 9948 0256", website="https://manlygolf.com.au/", source="directory", note="Private club. Listed as by invitation only."),
 new("terrey-hills", "Terrey Hills Golf & Country Club", "Duffys Forest", -33.68, 151.21, status="members", phone="(02) 9450 0155", website="https://www.terreyhillsgolf.com.au/", source="club", note="Private club. Members can book for unaccompanied visitors."),
 new("elanora", "Elanora Country Club", "Elanora Heights", -33.70, 151.28, status="members", phone="(02) 9913 7336", website="https://www.elanoracc.com.au/", email="sportadmin@elanoracc.com.au", source="club", note="Private club. Guests must be with a member. Interstate and overseas club members can request times by email, with a letter of introduction."),
 new("cromer", "Cromer Golf Club", "Cromer", -33.74, 151.27, status="members", phone="(02) 9982 3088", address="Cromer Rd, Cromer", website="https://cromergolfclub.com.au/", source="directory", note="Private club. Listed as by invitation only."),
 new("cronulla", "Cronulla Golf Club", "Cronulla", -34.05, 151.14, status="members", website="https://www.cronullagolf.com.au/", source="club", note="Private club. Reciprocal club visitors are welcome, with limits from May to August. Directories disagree on the phone number."),
 new("avondale", "Avondale Golf Club", "Pymble", -33.75, 151.14, status="members", phone="(02) 9449 6455", address="Avon Rd, Pymble", website="https://www.avondalegolfclub.com.au/", source="directory", note="Private club. Guests must be with a member."),
 new("killara", "The Killara Golf Club", "Killara", -33.76, 151.16, status="members", phone="(02) 9498 2700", address="556 Pacific Hwy, Killara", website="https://www.kgc.com.au/", source="directory", note="Private club. Visitors must be hosted by a member."),
 new("roseville", "Roseville Golf Club", "Roseville", -33.78, 151.20, status="members", source="directory", note="Private club. We couldn't confirm its phone number."),
 new("australian", "The Australian Golf Club", "Rosebery", -33.92, 151.21, status="members", website="https://www.australiangolfclub.com/", source="club", note="Private club. Guests need a letter of introduction from a recognised club."),
 new("royal-sydney", "The Royal Sydney Golf Club", "Rose Bay", -33.87, 151.27, status="members", phone="(02) 8362 7000", source="directory", note="Private club. Play is by member invitation or a reciprocal introduction."),
 # Details still missing
 new("pymble", "Pymble Golf Club", "Pymble", -33.74, 151.14, website="https://pymblegolf.com.au/", source="directory", note="We couldn't confirm its visitor policy or phone number. See the club's website."),
 new("pennant-hills", "Pennant Hills Golf Club", "Pennant Hills", -33.74, 151.07, website="https://www.pennanthillsgolfclub.com.au/", source="club", note="The club's website has a visitor information section. We couldn't confirm its phone number."),
]

shutil.copy(P("data", "courses.json"), P("data", "courses.before-details.json"))
d = json.load(open(P("data", "courses.json"), encoding="utf-8"))
by = {c["id"]: c for c in d}
assert not set(UPDATES) - set(by), set(UPDATES) - set(by)
n = 0
for cid, u in UPDATES.items():
    c = by[cid]
    c.update(u, checked=CHECKED); n += 1
    if c.get("note") is None:
        c.pop("note", None)
added = 0
for c in NEW:
    if c["id"] in by:
        by[c["id"]].update(c, checked=CHECKED)
    else:
        d.append(dict(c, checked=CHECKED)); added += 1
json.dump(d, open(P("data", "courses.json"), "w", encoding="utf-8"), indent=1)
shutil.copy(P("data", "courses.json"), P("site", "courses.json"))
print(f"Updated {n} courses, added {added}. {len(d)} in the directory, {sum(1 for c in d if c.get('enabled'))} with live times.")
