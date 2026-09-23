<p align="center">
  <img src="https://raw.githubusercontent.com/SuperFurias/maxurl/master/resources/imu_opera_banner_transparent.png" alt="Image Max URL" title="Image Max URL" />
</p>

---

> **IMU Fixed — fork of [qsniyg/maxurl](https://github.com/qsniyg/maxurl) by SuperFurias.**
> Same 10,000-site engine, plus performance fixes, a runtime per-site blocklist,
> centered popups by default, a global reset button, corrected modified-row flags,
> brute-force rules off by default, and de-noised background logging.
> Full change log and build notes: [`imu-fixed/extension-README.md`](imu-fixed/extension-README.md).
> Fork issues: [SuperFurias/maxurl/issues](https://github.com/SuperFurias/maxurl/issues).
> License: Apache-2.0 (see [LICENSE](LICENSE)).
> Original work © 2018–2024 qsniyg; fork modifications © 2026 SuperFurias.
> Fork builds carry their own extension ID (new installs; migrate settings
> via options Export/Import).

**Use it unpacked:** `python imu-fixed/build_extension.py`, then
`chrome://extensions` → Developer mode → Load unpacked → `imu-fixed-extension/`.
**Rebuild the engine after pulling upstream:** `python imu-fixed/apply_source_patches.py`
(if any assert names a drifted anchor, update it), then `npm install && npm run build`.

## Why this fork exists

After years on the original extension: with it enabled, YouTube Shorts icons (comments, title, likes, etc.) take a very long time to load while scrolling, unless `https://www.youtube.com/` is added under Rules > Disabled websites. Cause: the extension injects its full content script on every page and frame and holds blocking `webRequest` listeners on all traffic; on Shorts that contends with the late-hydrating UI. This fork exists to eliminate that cost (gated listeners, idle single-frame injection, per-site disable) while keeping the extension working everywhere else.

## Fork vs original

| Area | Original | This fork |
|---|---|---|
| YouTube Shorts icon lag | Full content script on every page/frame + always-on blocking `webRequest` listeners; Shorts icons crawl unless youtube.com is excluded (no per-site switch exists) | `document_idle` single-frame injection; two-key fast-bail skips heavy init on disabled/blocklisted hosts; background listeners attach/detach dynamically — zero request overhead where disabled |
| Console spam | Unguarded `tabs.sendMessage` fan-outs, hotload `executeScript` errors, unanswered setvalue/redirect messages | Guarded sends, hotload guards, every message answered, checked storage writes with a single quota warning |
| Per-site disable | Not available | Rules > Disabled websites (comma-separated, subdomains match); background enforces it per request too |
| Popup position | Anchored at cursor | Centered by default |
| Options reset | None | Global Reset button (companion script) |
| "Modified" flags | Dark mode and rule toggles show phantom modified rows | Defaults mirrored so only real edits flag |
| Brute-force rules | Default ON despite their own ban warning | Forced OFF by default |
| Distribution | Upstream-signed builds, Firefox XPI included | Chromium-packed CRX under its own extension ID with fork self-update feed; `LICENSE.txt` shipped inside; Firefox/XPI removed |
| Support | Upstream issues | Fork issues + rebuild docs (`imu-fixed/`) |

---

<p align="center">
  <b>English</b> | <a href="docs/pt/README.pt-BR.md">Português (Brasil)</a>
</p>

---

Image Max URL is a program that will try to find larger/original versions of images and videos, usually by replacing URL patterns.

It currently contains support for \>10,000 hardcoded websites (full list in [sites.txt](https://github.com/qsniyg/maxurl/blob/master/sites.txt)),
but it also supports a number of generic engines (such as Wordpress and MediaWiki), which means it can work for many other websites as well.

It is currently released as:

- Userscript: (most browsers)
  - Stable: [userscript_smaller.user.js](https://github.com/SuperFurias/maxurl/blob/master/userscript_smaller.user.js?raw=true) or [OpenUserJS](https://openuserjs.org/scripts/qsniyg/Image_Max_URL)
  - Development: [userscript.user.js](https://github.com/SuperFurias/maxurl/blob/master/userscript.user.js?raw=true) (recommended)
  - It serves as the base for everything listed below. It also serves as a node module (used by the reddit bot), and can be embedded in a website.
- Browser extension (Chromium-based browsers, e.g. Chrome): [ImageMaxURL_crx3.crx](https://github.com/SuperFurias/maxurl/blob/master/build/ImageMaxURL_crx3.crx) (fork-signed; carries its own extension ID, see [Sideloading](#sideloading-the-extension))
  - Unpacked loads from this git repository also work.
  - Since extensions have more privileges than userscripts, it has a bit of extra functionality over the userscript.
  - If YouTube (or another heavy site) misbehaves with the extension loaded, add its domain under Rules > Disabled websites in the options — that is upstream behavior (full-page injection), not a fork bug; the per-site list exists for exactly these sites.
  - Source code is in [manifest.json](https://github.com/SuperFurias/maxurl/blob/master/manifest.json) and the [extension](https://github.com/SuperFurias/maxurl/tree/master/extension) folder.
- [Website](https://qsniyg.github.io/maxurl/)
  - Due to browser security constraints, some URLs (requiring cross-origin requests) can't be supported by the website.
  - Source code is in the [gh-pages](https://github.com/qsniyg/maxurl/tree/gh-pages) branch.
- Reddit bot ([/u/MaxImageBot](https://www.reddit.com/user/MaxImageBot/))
  - Source code is in [reddit-bot/comment-bot.js](https://github.com/SuperFurias/maxurl/blob/master/reddit-bot/comment-bot.js) and [reddit-bot/dourl.js](https://github.com/SuperFurias/maxurl/blob/master/reddit-bot/dourl.js)

Community:

- [Discord Server](https://discord.gg/fH9Pf54)
- [Matrix](https://matrix.to/#/#image-max-url:tedomum.net?via=tedomum.net) (`#image-max-url:tedomum.net`)
- [Subreddit](http://reddit.com/r/MaxImage)

# Sideloading the extension

The extension is currently unavailable to other browsers\' addon stores (such as Chrome and Microsoft Edge),
but you can sideload this repository if you wish to use the extension version instead of the userscript.

- Repository:
  - Download the repository however you wish (I\'d recommend cloning it through git as it allows easier updating)
  - Chromium:
    - Go to <chrome://extensions>, make sure "Developer mode" is enabled, click "Load unpacked [extension]", and navigate to the maxurl repository
- CRX (Chromium-based browsers):
  - Download the CRX build from <https://github.com/SuperFurias/maxurl/blob/master/build/ImageMaxURL_crx3.crx> (fork-signed; carries a new extension ID, see below)
  - Go to <chrome://extensions>, make sure "Developer mode" is enabled, then drag&drop the downloaded CRX file onto the page. Disable/remove the upstream extension first (different extension ID — running both double-injects content scripts and webRequest handlers).

# Contributing

Any contribution is greatly appreciated! If you have any bug reports, feature requests, or new websites you want supported, please file an issue here.

If you don't have a Github account, feel free to either use one of the community links above or [contact me directly](https://qsniyg.github.io/).

If you wish to contribute to the repository itself (code contributions, translations, etc.), please check [CONTRIBUTING.md](https://github.com/qsniyg/maxurl/blob/master/CONTRIBUTING.md)
for more information.

# Integrating IMU in your program

As mentioned above, userscript.user.js also functions as a node module.

```js
var maximage = require('./userscript.user.js');

maximage(smallimage, {
  // If set to false, it will return only the URL if there aren't any special properties
  // Recommended to keep true.
  //
  // The only reason this option exists is as a small hack for a helper userscript used to find new rules,
  //  to check if IMU already supports a rule.
  fill_object: true,

  // Maximum amount of times it should be run.
  // Recommended to be at least 5.
  iterations: 200,

  // Whether or not to store to, and use an internal cache for URLs.
  // Set this to "read" if you want to use the cache without storing results to it.
  use_cache: true,

  // Timeout (in seconds) for cache entries in the URL cache
  urlcache_time: 60*60,

  // List of "problems" (such as watermarks or possibly broken image) to exclude.
  //
  // By default, all problems are excluded.
  // You can access the excluded problems through maximage.default_options.exclude_problems
  // By setting it to [], no problems will be excluded.
  //exclude_problems: [],

  // Whether or not to exclude videos
  exclude_videos: false,

  // This will include a "history" of objects found through iterations.
  // Disabling this will only keep the objects found through the last successful iteration.
  include_pastobjs: true,

  // This will try to find the original page for an image, even if it requires extra requests.
  force_page: false,

  // This allows rules that use 3rd-party websites to find larger images
  allow_thirdparty: false,

  // This is useful for implementing a blacklist or whitelist.
  //  If unspecified, it accepts all URLs.
  filter: function(url) {
    return true;
  },

  // Helper function to perform HTTP requests, used for sites like Flickr
  //  The API is expected to be like GM_xmlHTTPRequest's API.
  // An implementation using node's request module can be found in reddit-bot/dourl.js
  do_request: function(options) {
    // options = {
    //   url: "",
    //   method: "GET",
    //   data: "", // for method: "POST"
    //   overrideMimeType: "", // used to decode alternate charsets
    //   headers: {}, // If a header is null or "", don't include that header
    //   onload: function(resp) {
    //     // resp is expected to be XMLHttpRequest-like object, implementing these fields:
    //     //   finalUrl
    //     //   readyState
    //     //   responseText
    //     //   status
    //   }
    // }
  },

  // Callback
  cb: function(result) {
    if (!result)
      return;

    if (result.length === 1 && result[0].url === smallimage) {
       // No larger image was found
       return;
    }

    for (var i = 0; i < result.length; i++) {
      // Do something with the object
    }
  }
});
```

The result is a list of objects that contain properties that may be useful in using the returned image(s):

```js
[{
  // The URL of the image
  url: null,

  // Whether or not this URL is a video
  video: false,

  // Whether it's expected that it will always work or not.
  //  Don't rely on this value if you don't have to
  always_ok: false,

  // Whether or not the URL is likely to work.
  likely_broken: false,

  // Whether or not the server supports a HEAD request.
  can_head: true,

  // HEAD errors that can be ignored
  head_ok_errors: [],

  // Whether or not the server might return the wrong Content-Type header in the HEAD request
  head_wrong_contenttype: false,

  // Whether or not the server might return the wrong Content-Length header in the HEAD request
  head_wrong_contentlength: false,

  // This is used in the return value of the exported function.
  //  If you're using a callback (as shown in the code example above),
  //  this value will always be false
  waiting: false,

  // Whether or not the returned URL is expected to redirect to another URL
  redirects: false,

  // Whether or not the URL is temporary/only works on the current IP (such as a generated download link)
  is_private: false,

  // Whether or not the URL is expected to be the original image stored on the website's servers.
  is_original: false,

  // If this is true, you shouldn't input this URL again into IMU.
  norecurse: false,

  // Whether or not this URL should be used.
  // If true, treat this like a 404
  // If "mask", this image is an overlayed mask
  bad: false,

  // Same as above, but contains a list of objects, e.g.:
  // [{
  //    headers: {"Content-Length": "1000"},
  //    status: 301
  // }]
  // If one of the objects matches the response, it's a bad image.
  // You can use maximage.check_bad_if(bad_if, resp) to check.
  //  (resp is expected to be an XHR-like object)
  bad_if: [],

  // Whether or not this URL is a "fake" URL that was used internally (i.e. if true, don't use this)
  fake: false,

  // Headers required to view the returned URL
  //  If a header is null, don't include that header.
  headers: {},

  // Additional properties that could be useful
  extra: {
    // The original page where this image was hosted
    page: null,

    // The title/caption attached to the image
    caption: null
  },

  // If set, this is a more descriptive filename for the image
  filename: "",

  // A list of problems with this image. Use exclude_problems to exclude images with specific problems
  problems: {
    // If true, the image is likely larger than the one inputted, but it also has a watermark (when the inputted one doesn't)
    watermark: false,

    // If true, the image is likely smaller than the one inputted, but it has no watermark
    smaller: false,

    // If true, the image might be entirely different from the one inputted
    possibly_different: false,

    // If true, the image might be broken (such as GIFs on Tumblr)
    possibly_broken: false
  }
}]
```
