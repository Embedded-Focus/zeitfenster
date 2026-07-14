(function () {
    var HEX_COLOR_PATTERN = /^#[0-9a-fA-F]{3,8}$/;
    var MAX_TITLE_LENGTH = 100;

    function getOverrides() {
        var params = new URLSearchParams(window.location.search);
        return {
            primary: params.get("primary"),
            logo: params.get("logo"),
            title: params.get("title"),
        };
    }

    function applyPrimaryColor(value) {
        if (!value || !HEX_COLOR_PATTERN.test(value)) {
            return;
        }
        var root = document.documentElement.style;
        root.setProperty("--pico-primary", value);
        root.setProperty("--pico-primary-background", value);
        root.setProperty("--pico-primary-border", value);
        root.setProperty("--pico-primary-hover", value);
        root.setProperty("--pico-primary-hover-background", value);
        root.setProperty("--pico-primary-hover-border", value);
        root.setProperty("--pico-form-element-active-border-color", value);
    }

    function applyLogo(value) {
        if (!value) {
            return;
        }
        var parsed;
        try {
            parsed = new URL(value, window.location.href);
        } catch (error) {
            return;
        }
        if (parsed.protocol !== "https:") {
            return;
        }

        var logoImg = document.querySelector("img.logo");
        if (logoImg) {
            logoImg.src = parsed.href;
        }

        var favicon = document.querySelector('link[rel="icon"]');
        if (favicon) {
            favicon.href = parsed.href;
        }
    }

    function applyTitle(value) {
        if (!value) {
            return;
        }
        var trimmed = value.trim().slice(0, MAX_TITLE_LENGTH);
        if (!trimmed) {
            return;
        }
        document.title = trimmed;
        var heading = document.querySelector(".brand-copy h1");
        if (heading) {
            heading.textContent = trimmed;
        }
    }

    function applyOverrides() {
        var overrides = getOverrides();
        applyPrimaryColor(overrides.primary);
        applyLogo(overrides.logo);
        applyTitle(overrides.title);
    }

    function postHeight() {
        if (window.parent === window) {
            return;
        }
        window.parent.postMessage(
            {
                type: "zeitfenster:resize",
                height: document.documentElement.scrollHeight,
            },
            "*"
        );
    }

    function observeResize() {
        if (window.parent === window) {
            return;
        }
        postHeight();
        if (typeof ResizeObserver === "undefined") {
            return;
        }
        var observer = new ResizeObserver(postHeight);
        observer.observe(document.body);
    }

    applyOverrides();
    observeResize();
})();
