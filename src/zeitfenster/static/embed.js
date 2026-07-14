(function () {
    var MIN_HEIGHT = 200;
    var MAX_HEIGHT = 5000;
    var DEFAULT_HEIGHT = 600;

    function parsePositiveInt(value) {
        var parsed = parseInt(value, 10);
        if (isNaN(parsed) || parsed <= 0) {
            return null;
        }
        return parsed;
    }

    function resolveHeightBounds(script) {
        var min = parsePositiveInt(script.dataset.minHeight);
        var max = parsePositiveInt(script.dataset.maxHeight);
        var defaultHeight = parsePositiveInt(script.dataset.defaultHeight);

        if (min === null) {
            min = MIN_HEIGHT;
        }
        if (max === null) {
            max = MAX_HEIGHT;
        }
        if (min > max) {
            min = MIN_HEIGHT;
            max = MAX_HEIGHT;
        }
        if (defaultHeight === null) {
            defaultHeight = DEFAULT_HEIGHT;
        }

        return { min: min, max: max, defaultHeight: defaultHeight };
    }

    function buildIframeUrl(baseUrl, script) {
        var url = new URL(baseUrl);
        ["primary", "logo", "title"].forEach(function (name) {
            var value = script.dataset[name];
            if (value) {
                url.searchParams.set(name, value);
            }
        });
        return url.toString();
    }

    function findTarget(script) {
        var selector = script.dataset.target;
        if (selector) {
            var target = document.querySelector(selector);
            if (target) {
                return target;
            }
        }
        return null;
    }

    function createIframe(script, origin, bounds) {
        var iframe = document.createElement("iframe");
        iframe.src = buildIframeUrl(script.dataset.src, script);
        iframe.title = script.dataset.title || "Book a meeting";
        iframe.style.width = "100%";
        iframe.style.border = "0";
        iframe.style.height = bounds.defaultHeight + "px";
        iframe.dataset.zeitfensterOrigin = origin;
        return iframe;
    }

    function clampHeight(height, bounds) {
        return Math.min(Math.max(height, bounds.min), bounds.max);
    }

    function listenForResize(iframe, origin, bounds) {
        window.addEventListener("message", function (event) {
            if (event.origin !== origin || event.source !== iframe.contentWindow) {
                return;
            }
            var data = event.data;
            if (
                !data ||
                data.type !== "zeitfenster:resize" ||
                typeof data.height !== "number" ||
                !isFinite(data.height) ||
                data.height <= 0
            ) {
                return;
            }
            iframe.style.height = clampHeight(data.height, bounds) + "px";
        });
    }

    function init() {
        var script = document.currentScript;
        if (!script || !script.dataset.src) {
            return;
        }

        var origin = new URL(script.dataset.src).origin;
        var bounds = resolveHeightBounds(script);
        var iframe = createIframe(script, origin, bounds);
        var target = findTarget(script);

        if (target) {
            target.appendChild(iframe);
        } else if (script.parentNode) {
            script.parentNode.insertBefore(iframe, script.nextSibling);
        }

        listenForResize(iframe, origin, bounds);
    }

    init();
})();
