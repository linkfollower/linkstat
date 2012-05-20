#!/usr/bin/python

#   Copyright 2012 Linkfollower
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.
#
#
#  
# Set variable just_load in main to False if fetching links from the web
# and generate the graph from scratch.
# Set just_load to True if to post process an existing
# graph (graphml).
#
# Set varialble only_blogs in main to True if only to consider blogs in the
# post processed graph. Set to False if considering all
# types of online entries.
#
# Set variable name in main to the basename of the indata file to use 
# (without extension).
# In case just_load set to False, then indata will be based on
# the corresponding .ssv file.
# In case just_load set to True, then indata will be based on
# the corresponding .graphml file.
#
# Other files that are assumed to be present (empty files are fine).
# force_links.txt   - Contains source and destination urls to force
#                     a connection between entries.
# comments.txt      - Contains keywords in urls that are assumed if 
#                     found to be treated as next comment links in the
#                     page, i.e. they will be merged with the root url.
# renamed_links.txt - Contains renamed url mapping, in case several
#                     variants exists.
# dontload.txt      - Urls that will not be fetched and parsed,
#                     due to bad html that will crash the program.
#                     Typically links from these urls are added
#                     via the force_links.txt file instead.

import re
import mechanize
import cookielib
from mechanize import Browser,LinkNotFoundError
import sys
import os 
from igraph import *

# Init browser
def init_browser(br):

    # Cookie Jar
    cj = cookielib.LWPCookieJar()
    br.set_cookiejar(cj)

    # Browser options
    br.set_handle_equiv(True)
    br.set_handle_gzip(True)
    br.set_handle_redirect(True)
    br.set_handle_referer(True)
    br.set_handle_robots(False)

    # Follows refresh 0 but not hangs on refresh > 0
    br.set_handle_refresh(mechanize._http.HTTPRefreshProcessor(), max_time=1)

    # Want debugging messages?
    #br.set_debug_http(True)
    #br.set_debug_redirects(True)
    #br.set_debug_responses(True)

    # User-Agent (this is cheating, ok?)
    br.addheaders = [('User-agent', 'Mozilla/5.0 (X11; U; Linux i686; en-US; rv:1.9.0.1) Gecko/2008071615 Fedora/3.0.1-1.fc9 Firefox/3.0.1')]

def dump_graph_ids(prefix, g):
    skip = True
    skip = False
    if skip:
        return
    for v in range(0, len(g.vs)):
        if v != g.vs[v].index:
            raise BaseException("vertex index not as expected.")
        print "%s*%d*%s" % (prefix, v, g.vs[v]["url"])

def load_force_links(filename):
    force_links = []
    
    f = open(filename, 'r')
    for line in f:
        cur_line = line.rstrip()
        cur_str = str(cur_line)
        split_str = cur_str.split('*')
        if len(split_str) != 2:
            raise BaseException("Force links file corrupt")
        force_links.append(split_str)

    return force_links


def load_renamed_links(filename, wdict):
    # Key is renamed link that doesn't work
    # Value is working link
    rename_map = {}

    f = open(filename, 'r');
    for line in f:
        cur_line = line.rstrip()
        cur_str = str(cur_line)
        split_str = cur_str.split('*')
        key = split_str[0]
        value = split_str[1]
        if value in wdict:
            print "Detected working url %s in wdict" % (value)
            rename_map[key] = value
        else:
            print "Did not find working url %s in wdict" % (value)

    return rename_map;

# Read dict from file
def read_skv_dict_file(filename):
    f = open(filename, 'r')
    d = {}
    i = 0
    for line in f:
        cur_url = line.rstrip()
        #print cur_url
        cur_str = str(cur_url)
        split_str = cur_str.split('*')
        key = split_str[2]
        value = [i]
        value.extend(split_str)
        for j in range(len(value)):
            print 'value[%d]=%s' % (j, value[j])
        if key in d:
            print "Unon unique key %s" % (key)
            raise BaseException('Dict not unique')
        d[key] = value
        i += 1
    f.close()
    return d

def read_dict_file(filename):
    f = open(filename, 'r')
    d = {}
    i = 0
    for line in f:
        cur_url = line.rstrip()
        #print cur_url
        cur_str = str(cur_url)
        #print cur_str
        if cur_str in d:
            raise BaseException('Dict not unique')
        d[cur_str] = i
        i += 1
    f.close()
    return d

# Read set from file
def read_set_file(filename):
    f = open(filename, 'r')
    tmp = []
    for line in f:
        tmp.append(line.rstrip())
    s = set(tmp)
    f.close()
    return s

def get_url_variants(url):
    orig_url = url
    variants = [url]
    reg_exps = ["/$", ";.*$", "#.*$", "\?.*$", "/$"]

    for r in reg_exps:
        tmp = re.sub(r, "", url)
        if tmp != url:
            url = tmp
            variants.append(url)

    if len(variants) > 1:
        print 'variants for url %s: %s' % (orig_url, variants)

    return variants
        
def handle_url(recursion, from_id, url, br, outgoing_links, linked_urls, linked_urls_processed, wdict, cset, rename_map, g):
    print 'handle_url called with recursion %d' % (recursion)
    for l in br.links():
        link = str(l.url)
        #print 'Found link ' + link
        if link not in linked_urls:
            #print 'About to check %s for comments' % (link)
            for c in cset:
                if c in link:
                    # Found among comment urls, add to linked urls and continue
                    print 'Rec %d, Found comment substring %s in url %s' % (recursion, c, link)
                    linked_urls.add(link)
                    continue
        else:
            # Already among linked urls
            #print 'Rec %d, Already found %s in linked_urls' % (recursion, link)
            continue

        # If we get here, it is a link to be processed.
        if link in wdict:
            print 'Rec %d, Found %s in whitelist' % (recursion, link)
            if link.lower() not in outgoing_links:
                # Not already added as outgoing link.
                from_id = wdict[url]
                to_id = wdict[link]
                print '%d -> %d' % (from_id, to_id)
                g.add_edges([(from_id,to_id)]);
                outgoing_links.add(link.lower())
                print 'Rec %d, Adding new link %d -> %d' % (recursion, from_id, to_id)
            else:
                # Already found as outgoing link
                print 'Already found in outgoing links for this url'

    # Check everything in the dict against the html response.
    html = br.response().get_data()
    for w in wdict:
        if w == url:
            continue
        url_variants = get_url_variants(w)
        for variant in url_variants:
           if variant.lower() in html.lower():
               if variant != w:
                   print 'XXX: Found variant url link:'
                   print 'Orig link: ' + w
                   print 'Variant link: ' + variant
               if w.lower() not in outgoing_links:
                   print 'Rec %d, found %s as new link in plain text html' % (recursion, w)
                   # Not already added as outgoing link.
                   from_id = wdict[url]
                   to_id = wdict[w]
                   print '%d -> %d' % (from_id, to_id)
                   g.add_edges([(from_id,to_id)]);
                   outgoing_links.add(link.lower())
                   print 'Rec %d, Adding new link %d -> %d' % (recursion, from_id, to_id)
                   # Jump out of variant for loop.
                   break

    # Check the synonyms
    for r in rename_map:
        w = rename_map[r]
        if w == url:
            continue
        url_variants = get_url_variants(r)
        for variant in url_variants:
           if variant.lower() in html.lower():
               if variant != r:
                   print 'XXX: Synonym: Found variant url link:'
                   print 'Synonym: Orig link: ' + r
                   print 'Synonym: Variant link: ' + variant
               if w.lower() not in outgoing_links:
                   print 'Synonym: Rec %d, found %s -> %s as new link in plain text html' % (recursion, r, w)
                   # Not already added as outgoing link.
                   from_id = wdict[url]
                   to_id = wdict[w]
                   print 'Synonym: %d -> %d' % (from_id, to_id)
                   g.add_edges([(from_id,to_id)]);
                   outgoing_links.add(w.lower())
                   print 'Synonym: Rec %d, Adding new link %d -> %d' % (recursion, from_id, to_id)
                   # Jump out of variant for loop.
                   break

    # Recursively call again.

    something_was_processed = True
    while something_was_processed:
        something_was_processed = False
        for next_url in linked_urls:
            if next_url not in linked_urls_processed:
                # Process this one.
                linked_urls_processed.add(next_url)
                try:
                    br.open(next_url, timeout=30.0)
                except:
                    print 'Warning: Detected broken next_url: ' + next_url
                    g.vs[wdict[url]]["alive"] = "dead"
                    continue
                g.vs[wdict[url]]["alive"] = "alive"
                handle_url(recursion + 1, from_id, url, br, outgoing_links, linked_urls, linked_urls_processed, wdict, cset, rename_map, g)
                something_was_processed = True
                break

def plot_graph(g, name):
    layout = g.layout("fr")

    color_dict = {"A": "red", "B": "green", "C": "blue"}
    shape_dict = {"Blog" : "circle", "Online news" : "rectangle", "Statement" : "triangle-up", "Feature story" : "triangle-up", "Press release" : "triangle-down"}  
    size_dict = {"alive" : 10, "dead" : 20, "cannot parse" : 10}
    visual_style = {}
    visual_style["vertex_size"] = [size_dict[alive] for alive in g.vs["alive"]]
    visual_style["vertex_color"] = [color_dict[root] for root in g.vs["root"]]
    visual_style["vertex_shape"] = [shape_dict[medium] for medium in g.vs["medium"]]
    visual_style["vertex_label_color"] = 'black'
    visual_style["edge_color"] = 'gray42'
    visual_style["vertex_label_size"] = '15'

    visual_style["bbox"] = (1024,1024)
    visual_style["layout"] = layout
    plot(g, name + '.pdf', **visual_style)
    plot(g, name + '.svg', **visual_style)
    plot(g, name + '.png', **visual_style)

def main(name):
    # Browser
    br = mechanize.Browser()

    init_browser(br)
    
    skvdict = read_skv_dict_file(name + '.ssv')
    wdict = {}
    for i in skvdict:
        wdict[i] = skvdict[i][0]

    rename_map = load_renamed_links("renamed_links.txt", wdict)

    cset = read_set_file('comments.txt')
    
    dontloadset = read_dict_file('dontload.txt')

    print 'Initializing graph with %d nodes' % (len(wdict))
    g = Graph(len(wdict), directed=True)

    for key in skvdict:
        #print 'key %s = %d ' % (key, wdict[key])
        #g.vs[wdict[key]]["name"] = key
        # Id;Date;Medium;Direct link;Sender;Content;Root
        value = skvdict[key]
        g.vs[value[0]]["date"] = value[1]
        g.vs[value[0]]["medium"] = value[2]
        g.vs[value[0]]["url"] = value[3]
        g.vs[value[0]]["sender"] = value[4]
        g.vs[value[0]]["content"] = value[5]
        g.vs[value[0]]["root"] = value[6]

    for i in wdict:
        url = i

        if url in dontloadset:
            print "Skipping non parseable url %s" % (url)
            from_id = wdict[url]
            g.vs[from_id]["alive"] = "cannot parse"
            g.vs[from_id]["title"] = "Html not parsed"
            continue
            
        print 'Processing ' + url
        try:
            br.open(url, timeout=30.0)
        except:
            print 'Warning: Detected broken url: ' + url
            g.vs[wdict[url]]["alive"] = 'dead'
            continue
        g.vs[wdict[url]]["alive"] = "alive"
        from_id = wdict[url]
        title = str(br.title())
        print 'Id %d, Url %s has title %s' % (from_id, url, title)
        g.vs[from_id]["title"] = title

        linked_urls = set()
        linked_urls_processed = set()
        linked_urls.add(url);
        linked_urls_processed.add(url);
        outgoing_links = set()

        handle_url(0, from_id, url, br, outgoing_links, linked_urls, linked_urls_processed, wdict, cset, rename_map, g)

    plot_graph(g, name)

    g.save(name + '.graphml')

just_load = True
just_load = False

only_blogs = True
only_blogs = False

#name = 'gp_review5'
name = 'merged13'

print 'Using name ' + name

if (not just_load):
    main(name)
else:
    print 'Just loading and plotting.'
    g = load(name + '.graphml')

    plot_graph(g, name)

    # Add the forced links.
    force_links = load_force_links("force_links.txt")
    
    print "Force links:"
    print force_links
    for count in range(0, len(force_links)):
        from_link = force_links[count][0]
        to_link = force_links[count][1]
        from_id = -1
        to_id = -1
        for i in range(0, len(g.vs)):
            if g.vs[i]["url"] == to_link:
                to_id = i
            if g.vs[i]["url"] == from_link:
                from_id = i
        if from_id >= 0 and to_id >= 0:
            if from_id == to_id:
                raise BaseException("Forced link with same ids!")
            print "Found forced link %s -> %s" % (from_link, to_link)
            print "Adding forced link %d -> %d" % (from_id, to_id)
            g.add_edges([(from_id,to_id)]);
        else:
            print "Force link not found: %s -> %s" % (from_link, to_link)

    # Status.
    print g.degree(type="in")
    i = 0
    for d in g.degree(type="in"):
        if g.vs[i]["medium"] == "Blog":
            print "%d (id %d, type %s) -> %s" % (d, i, g.vs[i]["medium"], g.vs[i]["url"]) 
        i += 1

    for f in range(0, len(g.vs)):
        if g.vs[f]["medium"] != "Blog":
            continue
        only_links_to_non_blog = False
        for e in g.es:
            if e.source == f:
                if g.vs[e.target]["medium"] == "Blog":
                    #if only_links_to_non_blog:
                    #    print "%d also links to blog %d" % (f, e.target)
                    # Links to something else than blog.
                    only_links_to_non_blog = False
                    break 
                else:
                    #print "%d links to non blog %d" % (f, e.target)
                    only_links_to_non_blog = True
        if only_links_to_non_blog:
            print "Only links to non blogs. Id %d, Url %s" % (f, g.vs[f]["url"])
    
    if only_blogs:
        cont = True
        while (cont):
            none_removed = True
            for v in g.vs:
                if v["medium"] != "Blog":
                    none_removed = False 
                    print "Removing non blog"
                    print v
                    g.delete_vertices(v)
                    break
            if none_removed:
                cont = False

        # Print and save.
        dump_graph_ids(name + "_force_blogs", g)
        g.save(name + "_force_blogs.graphml")
        plot_graph(g, name + "_force_blogs")
    else:
       # Print and save.
       dump_graph_ids(name + "_force", g)
       g.save(name + "_force.graphml")
       plot_graph(g, name + "_force")

    # Remove vertices from the graph that have
    # no links to or from and that are not from root A.
    remove_vertices = g.vs.select(_degree_eq=0).select(root_ne="A")

    g.delete_vertices(remove_vertices)

    # Print and save.
    clean_name = name + "_clean"
    if only_blogs:
        clean_name = clean_name + "_blogs"

    dump_graph_ids(clean_name, g)
    g.save(clean_name + ".graphml")
    plot_graph(g, clean_name )
