(function webpackUniversalModuleDefinition(root, factory) {
  if(typeof exports === 'object' && typeof module === 'object')
    module.exports = factory();
  else if(typeof define === 'function' && define.amd)
    define([], factory);
  else if(typeof exports === 'object')
    exports["rrule"] = factory();
  else
    root["rrule"] = factory();
})(typeof self !== 'undefined' ? self : this, function() {
return /******/ (function(modules) { // webpackBootstrap
/******/  // The module cache
/******/  var installedModules = {};
/******/
/******/  // The require function
/******/  function __webpack_require__(moduleId) {
/******/
/******/    // Check if module is in cache
/******/    if(installedModules[moduleId]) {
/******/      return installedModules[moduleId].exports;
/******/    }
/******/    // Create a new module (and put it into the cache)
/******/    var module = installedModules[moduleId] = {
/******/      i: moduleId,
/******/      l: false,
/******/      exports: {}
/******/    };
/******/
/******/    // Execute the module function
/******/    modules[moduleId].call(module.exports, module, module.exports, __webpack_require__);
/******/
/******/    // Flag the module as loaded
/******/    module.l = true;
/******/
/******/    // Return the exports of the module
/******/    return module.exports;
/******/  }
/******/
/******/
/******/  // expose the modules object (__webpack_modules__)
/******/  __webpack_require__.m = modules;
/******/
/******/  // expose the module cache
/******/  __webpack_require__.c = installedModules;
/******/
/******/  // define getter function for harmony exports
/******/  __webpack_require__.d = function(exports, name, getter) {
/******/    if(!__webpack_require__.o(exports, name)) {
/******/      Object.defineProperty(exports, name, { enumerable: true, get: getter });
/******/    }
/******/  };
/******/
/******/  // define __esModule on exports
/******/  __webpack_require__.r = function(exports) {
/******/    if(typeof Symbol !== 'undefined' && Symbol.toStringTag) {
/******/      Object.defineProperty(exports, Symbol.toStringTag, { value: 'Module' });
/******/    }
/******/    Object.defineProperty(exports, '__esModule', { value: true });
/******/  };
/******/
/******/  // create a fake namespace object
/******/  // mode & 1: value is a module id, require it
/******/  // mode & 2: merge all properties of value into the ns
/******/  // mode & 4: return value when already ns object
/******/  // mode & 8|1: behave like require
/******/  __webpack_require__.t = function(value, mode) {
/******/    if(mode & 1) value = __webpack_require__(value);
/******/    if(mode & 8) return value;
/******/    if((mode & 4) && typeof value === 'object' && value && value.__esModule) return value;
/******/    var ns = Object.create(null);
/******/    __webpack_require__.r(ns);
/******/    Object.defineProperty(ns, 'default', { enumerable: true, value: value });
/******/    if(mode & 2 && typeof value != 'string') for(var key in value) __webpack_require__.d(ns, key, function(key) { return value[key]; }.bind(null, key));
/******/    return ns;
/******/  };
/******/
/******/  // getDefaultExport function for compatibility with non-harmony modules
/******/  __webpack_require__.n = function(module) {
/******/    var getter = module && module.__esModule ?
/******/      function getDefault() { return module['default']; } :
/******/      function getModuleExports() { return module; };
/******/    __webpack_require__.d(getter, 'a', getter);
/******/    return getter;
/******/  };
/******/
/******/  // Object.prototype.hasOwnProperty.call
/******/  __webpack_require__.o = function(object, property) { return Object.prototype.hasOwnProperty.call(object, property); };
/******/
/******/  // __webpack_public_path__
/******/  __webpack_require__.p = "";
/******/
/******/
/******/  // Load entry module and return exports
/******/  return __webpack_require__(__webpack_require__.s = 1);
/******/ })
/************************************************************************/
/******/ ([
/* 0 */
/***/ (function(module, __webpack_exports__, __webpack_require__) {

"use strict";
/* harmony export (binding) */ __webpack_require__.d(__webpack_exports__, "f", function() { return isPresent; });
/* harmony export (binding) */ __webpack_require__.d(__webpack_exports__, "e", function() { return isNumber; });
/* harmony export (binding) */ __webpack_require__.d(__webpack_exports__, "g", function() { return isWeekdayStr; });
/* harmony export (binding) */ __webpack_require__.d(__webpack_exports__, "d", function() { return isArray; });
/* harmony export (binding) */ __webpack_require__.d(__webpack_exports__, "k", function() { return range; });
/* unused harmony export clone */
/* harmony export (binding) */ __webpack_require__.d(__webpack_exports__, "l", function() { return repeat; });
/* harmony export (binding) */ __webpack_require__.d(__webpack_exports__, "n", function() { return toArray; });
/* harmony export (binding) */ __webpack_require__.d(__webpack_exports__, "i", function() { return padStart; });
/* harmony export (binding) */ __webpack_require__.d(__webpack_exports__, "m", function() { return split; });
/* harmony export (binding) */ __webpack_require__.d(__webpack_exports__, "j", function() { return pymod; });
/* harmony export (binding) */ __webpack_require__.d(__webpack_exports__, "a", function() { return divmod; });
/* harmony export (binding) */ __webpack_require__.d(__webpack_exports__, "b", function() { return empty; });
/* harmony export (binding) */ __webpack_require__.d(__webpack_exports__, "h", function() { return notEmpty; });
/* harmony export (binding) */ __webpack_require__.d(__webpack_exports__, "c", function() { return includes; });
/* harmony import */ var _weekday__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(2);
// =============================================================================
// Helper functions
// =============================================================================

var isPresent = function (value) {
    return value !== null && value !== undefined;
};
var isNumber = function (value) {
    return typeof value === 'number';
};
var isWeekdayStr = function (value) {
    return _weekday__WEBPACK_IMPORTED_MODULE_0__[/* ALL_WEEKDAYS */ "a"].indexOf(value) >= 0;
};
var isArray = Array.isArray;
/**
 * Simplified version of python's range()
 */
var range = function (start, end) {
    if (end === void 0) { end = start; }
    if (arguments.length === 1) {
        end = start;
        start = 0;
    }
    var rang = [];
    for (var i = start; i < end; i++)
        rang.push(i);
    return rang;
};
var clone = function (array) {
    return [].concat(array);
};
var repeat = function (value, times) {
    var i = 0;
    var array = [];
    if (isArray(value)) {
        for (; i < times; i++)
            array[i] = [].concat(value);
    }
    else {
        for (; i < times; i++)
            array[i] = value;
    }
    return array;
};
var toArray = function (item) {
    if (isArray(item)) {
        return item;
    }
    return [item];
};
function padStart(item, targetLength, padString) {
    if (padString === void 0) { padString = ' '; }
    var str = String(item);
    targetLength = targetLength >> 0;
    if (str.length > targetLength) {
        return String(str);
    }
    targetLength = targetLength - str.length;
    if (targetLength > padString.length) {
        padString += repeat(padString, targetLength / padString.length);
    }
    return padString.slice(0, targetLength) + String(str);
}
/**
 * Python like split
 */
var split = function (str, sep, num) {
    var splits = str.split(sep);
    return num
        ? splits.slice(0, num).concat([splits.slice(num).join(sep)])
        : splits;
};
/**
 * closure/goog/math/math.js:modulo
 * Copyright 2006 The Closure Library Authors.
 * The % operator in JavaScript returns the remainder of a / b, but differs from
 * some other languages in that the result will have the same sign as the
 * dividend. For example, -1 % 8 == -1, whereas in some other languages
 * (such as Python) the result would be 7. This function emulates the more
 * correct modulo behavior, which is useful for certain applications such as
 * calculating an offset index in a circular list.
 *
 * @param {number} a The dividend.
 * @param {number} b The divisor.
 * @return {number} a % b where the result is between 0 and b (either 0 <= x < b
 *     or b < x <= 0, depending on the sign of b).
 */
var pymod = function (a, b) {
    var r = a % b;
    // If r and b differ in sign, add b to wrap the result to the correct sign.
    return r * b < 0 ? r + b : r;
};
/**
 * @see: <http://docs.python.org/library/functions.html#divmod>
 */
var divmod = function (a, b) {
    return { div: Math.floor(a / b), mod: pymod(a, b) };
};
var empty = function (obj) {
    return !isPresent(obj) || obj.length === 0;
};
/**
 * Python-like boolean
 * @return {Boolean} value of an object/primitive, taking into account
 * the fact that in Python an empty list's/tuple's
 * boolean value is False, whereas in JS it's true
 */
var notEmpty = function (obj) {
    return !empty(obj);
};
/**
 * Return true if a value is in an array
 */
var includes = function (arr, val) {
    return notEmpty(arr) && arr.indexOf(val) !== -1;
};


/***/ }),
/* 1 */
/***/ (function(module, __webpack_exports__, __webpack_require__) {

"use strict";
__webpack_require__.r(__webpack_exports__);

// EXTERNAL MODULE: ./src/helpers.ts
var helpers = __webpack_require__(0);

// CONCATENATED MODULE: ./src/dateutil.ts

/**
 * General date-related utilities.
 * Also handles several incompatibilities between JavaScript and Python
 *
 */
var dateutil_dateutil;
(function (dateutil) {
    dateutil.MONTH_DAYS = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
    /**
     * Number of milliseconds of one day
     */
    dateutil.ONE_DAY = 1000 * 60 * 60 * 24;
    /**
     * @see: <http://docs.python.org/library/datetime.html#datetime.MAXYEAR>
     */
    dateutil.MAXYEAR = 9999;
    /**
     * Python uses 1-Jan-1 as the base for calculating ordinals but we don't
     * want to confuse the JS engine with milliseconds > Number.MAX_NUMBER,
     * therefore we use 1-Jan-1970 instead
     */
    dateutil.ORDINAL_BASE = new Date(Date.UTC(1970, 0, 1));
    /**
     * Python: MO-SU: 0 - 6
     * JS: SU-SAT 0 - 6
     */
    dateutil.PY_WEEKDAYS = [6, 0, 1, 2, 3, 4, 5];
    /**
     * py_date.timetuple()[7]
     */
    dateutil.getYearDay = function (date) {
        var dateNoTime = new Date(date.getUTCFullYear(), date.getUTCMonth(), date.getUTCDate());
        return (Math.ceil((dateNoTime.valueOf() -
            new Date(date.getUTCFullYear(), 0, 1).valueOf()) /
            dateutil.ONE_DAY) + 1);
    };
    dateutil.isLeapYear = function (year) {
        return (year % 4 === 0 && year % 100 !== 0) || year % 400 === 0;
    };
    dateutil.isDate = function (value) {
        return value instanceof Date;
    };
    dateutil.isValidDate = function (value) {
        return dateutil.isDate(value) && !isNaN(value.getTime());
    };
    /**
     * @return {Number} the date's timezone offset in ms
     */
    dateutil.tzOffset = function (date) {
        return date.getTimezoneOffset() * 60 * 1000;
    };
    /**
     * @see: <http://www.mcfedries.com/JavaScript/DaysBetween.asp>
     */
    dateutil.daysBetween = function (date1, date2) {
        // The number of milliseconds in one day
        // Convert both dates to milliseconds
        var date1ms = date1.getTime() - dateutil.tzOffset(date1);
        var date2ms = date2.getTime() - dateutil.tzOffset(date2);
        // Calculate the difference in milliseconds
        var differencems = date1ms - date2ms;
        // Convert back to days and return
        return Math.round(differencems / dateutil.ONE_DAY);
    };
    /**
     * @see: <http://docs.python.org/library/datetime.html#datetime.date.toordinal>
     */
    dateutil.toOrdinal = function (date) {
        return dateutil.daysBetween(date, dateutil.ORDINAL_BASE);
    };
    /**
     * @see - <http://docs.python.org/library/datetime.html#datetime.date.fromordinal>
     */
    dateutil.fromOrdinal = function (ordinal) {
        return new Date(dateutil.ORDINAL_BASE.getTime() + ordinal * dateutil.ONE_DAY);
    };
    dateutil.getMonthDays = function (date) {
        var month = date.getUTCMonth();
        return month === 1 && dateutil.isLeapYear(date.getUTCFullYear())
            ? 29
            : dateutil.MONTH_DAYS[month];
    };
    /**
     * @return {Number} python-like weekday
     */
    dateutil.getWeekday = function (date) {
        return dateutil.PY_WEEKDAYS[date.getUTCDay()];
    };
    /**
     * @see: <http://docs.python.org/library/calendar.html#calendar.monthrange>
     */
    dateutil.monthRange = function (year, month) {
        var date = new Date(Date.UTC(year, month, 1));
        return [dateutil.getWeekday(date), dateutil.getMonthDays(date)];
    };
    /**
     * @see: <http://docs.python.org/library/datetime.html#datetime.datetime.combine>
     */
    dateutil.combine = function (date, time) {
        time = time || date;
        return new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), date.getUTCDate(), time.getHours(), time.getMinutes(), time.getSeconds(), time.getMilliseconds()));
    };
    dateutil.clone = function (date) {
        var dolly = new Date(date.getTime());
        return dolly;
    };
    dateutil.cloneDates = function (dates) {
        var clones = [];
        for (var i = 0; i < dates.length; i++) {
            clones.push(dateutil.clone(dates[i]));
        }
        return clones;
    };
    /**
     * Sorts an array of Date or dateutil.Time objects
     */
    dateutil.sort = function (dates) {
        dates.sort(function (a, b) {
            return a.getTime() - b.getTime();
        });
    };
    dateutil.timeToUntilString = function (time, utc) {
        if (utc === void 0) { utc = true; }
        var date = new Date(time);
        return [
            Object(helpers["i" /* padStart */])(date.getUTCFullYear().toString(), 4, '0'),
            Object(helpers["i" /* padStart */])(date.getUTCMonth() + 1, 2, '0'),
            Object(helpers["i" /* padStart */])(date.getUTCDate(), 2, '0'),
            'T',
            Object(helpers["i" /* padStart */])(date.getUTCHours(), 2, '0'),
            Object(helpers["i" /* padStart */])(date.getUTCMinutes(), 2, '0'),
            Object(helpers["i" /* padStart */])(date.getUTCSeconds(), 2, '0'),
            utc ? 'Z' : ''
        ].join('');
    };
    dateutil.untilStringToDate = function (until) {
        var re = /^(\d{4})(\d{2})(\d{2})(T(\d{2})(\d{2})(\d{2})Z?)?$/;
        var bits = re.exec(until);
        if (!bits)
            throw new Error("Invalid UNTIL value: " + until);
        return new Date(Date.UTC(parseInt(bits[1], 10), parseInt(bits[2], 10) - 1, parseInt(bits[3], 10), parseInt(bits[5], 10) || 0, parseInt(bits[6], 10) || 0, parseInt(bits[7], 10) || 0));
    };
})(dateutil_dateutil || (dateutil_dateutil = {}));
/* harmony default export */ var src_dateutil = (dateutil_dateutil);

// CONCATENATED MODULE: ./src/iterresult.ts
/**
 * This class helps us to emulate python's generators, sorta.
 */
var IterResult = /** @class */ (function () {
    function IterResult(method, args) {
        this.minDate = null;
        this.maxDate = null;
        this._result = [];
        this.total = 0;
        this.method = method;
        this.args = args;
        if (method === 'between') {
            this.maxDate = args.inc
                ? args.before
                : new Date(args.before.getTime() - 1);
            this.minDate = args.inc ? args.after : new Date(args.after.getTime() + 1);
        }
        else if (method === 'before') {
            this.maxDate = args.inc ? args.dt : new Date(args.dt.getTime() - 1);
        }
        else if (method === 'after') {
            this.minDate = args.inc ? args.dt : new Date(args.dt.getTime() + 1);
        }
    }
    /**
     * Possibly adds a date into the result.
     *
     * @param {Date} date - the date isn't necessarly added to the result
     *                      list (if it is too late/too early)
     * @return {Boolean} true if it makes sense to continue the iteration
     *                   false if we're done.
     */
    IterResult.prototype.accept = function (date) {
        ++this.total;
        var tooEarly = this.minDate && date < this.minDate;
        var tooLate = this.maxDate && date > this.maxDate;
        if (this.method === 'between') {
            if (tooEarly)
                return true;
            if (tooLate)
                return false;
        }
        else if (this.method === 'before') {
            if (tooLate)
                return false;
        }
        else if (this.method === 'after') {
            if (tooEarly)
                return true;
            this.add(date);
            return false;
        }
        return this.add(date);
    };
    /**
     *
     * @param {Date} date that is part of the result.
     * @return {Boolean} whether we are interested in more values.
     */
    IterResult.prototype.add = function (date) {
        this._result.push(date);
        return true;
    };
    /**
     * 'before' and 'after' return only one date, whereas 'all'
     * and 'between' an array.
     * @return {Date,Array?}
     */
    IterResult.prototype.getValue = function () {
        var res = this._result;
        switch (this.method) {
            case 'all':
            case 'between':
                return res;
            case 'before':
            case 'after':
            default:
                return (res.length ? res[res.length - 1] : null);
        }
    };
    IterResult.prototype.clone = function () {
        return new IterResult(this.method, this.args);
    };
    return IterResult;
}());
/* harmony default export */ var iterresult = (IterResult);

// CONCATENATED MODULE: ./node_modules/tslib/tslib.es6.js
/*! *****************************************************************************
Copyright (c) Microsoft Corporation. All rights reserved.
Licensed under the Apache License, Version 2.0 (the "License"); you may not use
this file except in compliance with the License. You may obtain a copy of the
License at http://www.apache.org/licenses/LICENSE-2.0

THIS CODE IS PROVIDED ON AN *AS IS* BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
KIND, EITHER EXPRESS OR IMPLIED, INCLUDING WITHOUT LIMITATION ANY IMPLIED
WARRANTIES OR CONDITIONS OF TITLE, FITNESS FOR A PARTICULAR PURPOSE,
MERCHANTABLITY OR NON-INFRINGEMENT.

See the Apache Version 2.0 License for specific language governing permissions
and limitations under the License.
***************************************************************************** */
/* global Reflect, Promise */

var extendStatics = function(d, b) {
    extendStatics = Object.setPrototypeOf ||
        ({ __proto__: [] } instanceof Array && function (d, b) { d.__proto__ = b; }) ||
        function (d, b) { for (var p in b) if (b.hasOwnProperty(p)) d[p] = b[p]; };
    return extendStatics(d, b);
};

function __extends(d, b) {
    extendStatics(d, b);
    function __() { this.constructor = d; }
    d.prototype = b === null ? Object.create(b) : (__.prototype = b.prototype, new __());
}

var __assign = function() {
    __assign = Object.assign || function __assign(t) {
        for (var s, i = 1, n = arguments.length; i < n; i++) {
            s = arguments[i];
            for (var p in s) if (Object.prototype.hasOwnProperty.call(s, p)) t[p] = s[p];
        }
        return t;
    }
    return __assign.apply(this, arguments);
}

function __rest(s, e) {
    var t = {};
    for (var p in s) if (Object.prototype.hasOwnProperty.call(s, p) && e.indexOf(p) < 0)
        t[p] = s[p];
    if (s != null && typeof Object.getOwnPropertySymbols === "function")
        for (var i = 0, p = Object.getOwnPropertySymbols(s); i < p.length; i++) {
            if (e.indexOf(p[i]) < 0 && Object.prototype.propertyIsEnumerable.call(s, p[i]))
                t[p[i]] = s[p[i]];
        }
    return t;
}

function __decorate(decorators, target, key, desc) {
    var c = arguments.length, r = c < 3 ? target : desc === null ? desc = Object.getOwnPropertyDescriptor(target, key) : desc, d;
    if (typeof Reflect === "object" && typeof Reflect.decorate === "function") r = Reflect.decorate(decorators, target, key, desc);
    else for (var i = decorators.length - 1; i >= 0; i--) if (d = decorators[i]) r = (c < 3 ? d(r) : c > 3 ? d(target, key, r) : d(target, key)) || r;
    return c > 3 && r && Object.defineProperty(target, key, r), r;
}

function __param(paramIndex, decorator) {
    return function (target, key) { decorator(target, key, paramIndex); }
}

function __metadata(metadataKey, metadataValue) {
    if (typeof Reflect === "object" && typeof Reflect.metadata === "function") return Reflect.metadata(metadataKey, metadataValue);
}

function __awaiter(thisArg, _arguments, P, generator) {
    return new (P || (P = Promise))(function (resolve, reject) {
        function fulfilled(value) { try { step(generator.next(value)); } catch (e) { reject(e); } }
        function rejected(value) { try { step(generator["throw"](value)); } catch (e) { reject(e); } }
        function step(result) { result.done ? resolve(result.value) : new P(function (resolve) { resolve(result.value); }).then(fulfilled, rejected); }
        step((generator = generator.apply(thisArg, _arguments || [])).next());
    });
}

function __generator(thisArg, body) {
    var _ = { label: 0, sent: function() { if (t[0] & 1) throw t[1]; return t[1]; }, trys: [], ops: [] }, f, y, t, g;
    return g = { next: verb(0), "throw": verb(1), "return": verb(2) }, typeof Symbol === "function" && (g[Symbol.iterator] = function() { return this; }), g;
    function verb(n) { return function (v) { return step([n, v]); }; }
    function step(op) {
        if (f) throw new TypeError("Generator is already executing.");
        while (_) try {
            if (f = 1, y && (t = op[0] & 2 ? y["return"] : op[0] ? y["throw"] || ((t = y["return"]) && t.call(y), 0) : y.next) && !(t = t.call(y, op[1])).done) return t;
            if (y = 0, t) op = [op[0] & 2, t.value];
            switch (op[0]) {
                case 0: case 1: t = op; break;
                case 4: _.label++; return { value: op[1], done: false };
                case 5: _.label++; y = op[1]; op = [0]; continue;
                case 7: op = _.ops.pop(); _.trys.pop(); continue;
                default:
                    if (!(t = _.trys, t = t.length > 0 && t[t.length - 1]) && (op[0] === 6 || op[0] === 2)) { _ = 0; continue; }
                    if (op[0] === 3 && (!t || (op[1] > t[0] && op[1] < t[3]))) { _.label = op[1]; break; }
                    if (op[0] === 6 && _.label < t[1]) { _.label = t[1]; t = op; break; }
                    if (t && _.label < t[2]) { _.label = t[2]; _.ops.push(op); break; }
                    if (t[2]) _.ops.pop();
                    _.trys.pop(); continue;
            }
            op = body.call(thisArg, _);
        } catch (e) { op = [6, e]; y = 0; } finally { f = t = 0; }
        if (op[0] & 5) throw op[1]; return { value: op[0] ? op[1] : void 0, done: true };
    }
}

function __exportStar(m, exports) {
    for (var p in m) if (!exports.hasOwnProperty(p)) exports[p] = m[p];
}

function __values(o) {
    var m = typeof Symbol === "function" && o[Symbol.iterator], i = 0;
    if (m) return m.call(o);
    return {
        next: function () {
            if (o && i >= o.length) o = void 0;
            return { value: o && o[i++], done: !o };
        }
    };
}

function __read(o, n) {
    var m = typeof Symbol === "function" && o[Symbol.iterator];
    if (!m) return o;
    var i = m.call(o), r, ar = [], e;
    try {
        while ((n === void 0 || n-- > 0) && !(r = i.next()).done) ar.push(r.value);
    }
    catch (error) { e = { error: error }; }
    finally {
        try {
            if (r && !r.done && (m = i["return"])) m.call(i);
        }
        finally { if (e) throw e.error; }
    }
    return ar;
}

function __spread() {
    for (var ar = [], i = 0; i < arguments.length; i++)
        ar = ar.concat(__read(arguments[i]));
    return ar;
}

function __spreadArrays() {
    for (var s = 0, i = 0, il = arguments.length; i < il; i++) s += arguments[i].length;
    for (var r = Array(s), k = 0, i = 0; i < il; i++)
        for (var a = arguments[i], j = 0, jl = a.length; j < jl; j++, k++)
            r[k] = a[j];
    return r;
};

function __await(v) {
    return this instanceof __await ? (this.v = v, this) : new __await(v);
}

function __asyncGenerator(thisArg, _arguments, generator) {
    if (!Symbol.asyncIterator) throw new TypeError("Symbol.asyncIterator is not defined.");
    var g = generator.apply(thisArg, _arguments || []), i, q = [];
    return i = {}, verb("next"), verb("throw"), verb("return"), i[Symbol.asyncIterator] = function () { return this; }, i;
    function verb(n) { if (g[n]) i[n] = function (v) { return new Promise(function (a, b) { q.push([n, v, a, b]) > 1 || resume(n, v); }); }; }
    function resume(n, v) { try { step(g[n](v)); } catch (e) { settle(q[0][3], e); } }
    function step(r) { r.value instanceof __await ? Promise.resolve(r.value.v).then(fulfill, reject) : settle(q[0][2], r); }
    function fulfill(value) { resume("next", value); }
    function reject(value) { resume("throw", value); }
    function settle(f, v) { if (f(v), q.shift(), q.length) resume(q[0][0], q[0][1]); }
}

function __asyncDelegator(o) {
    var i, p;
    return i = {}, verb("next"), verb("throw", function (e) { throw e; }), verb("return"), i[Symbol.iterator] = function () { return this; }, i;
    function verb(n, f) { i[n] = o[n] ? function (v) { return (p = !p) ? { value: __await(o[n](v)), done: n === "return" } : f ? f(v) : v; } : f; }
}

function __asyncValues(o) {
    if (!Symbol.asyncIterator) throw new TypeError("Symbol.asyncIterator is not defined.");
    var m = o[Symbol.asyncIterator], i;
    return m ? m.call(o) : (o = typeof __values === "function" ? __values(o) : o[Symbol.iterator](), i = {}, verb("next"), verb("throw"), verb("return"), i[Symbol.asyncIterator] = function () { return this; }, i);
    function verb(n) { i[n] = o[n] && function (v) { return new Promise(function (resolve, reject) { v = o[n](v), settle(resolve, reject, v.done, v.value); }); }; }
    function settle(resolve, reject, d, v) { Promise.resolve(v).then(function(v) { resolve({ value: v, done: d }); }, reject); }
}

function __makeTemplateObject(cooked, raw) {
    if (Object.defineProperty) { Object.defineProperty(cooked, "raw", { value: raw }); } else { cooked.raw = raw; }
    return cooked;
};

function __importStar(mod) {
    if (mod && mod.__esModule) return mod;
    var result = {};
    if (mod != null) for (var k in mod) if (Object.hasOwnProperty.call(mod, k)) result[k] = mod[k];
    result.default = mod;
    return result;
}

function __importDefault(mod) {
    return (mod && mod.__esModule) ? mod : { default: mod };
}

// CONCATENATED MODULE: ./src/callbackiterresult.ts


/**
 * IterResult subclass that calls a callback function on each add,
 * and stops iterating when the callback returns false.
 */
var callbackiterresult_CallbackIterResult = /** @class */ (function (_super) {
    __extends(CallbackIterResult, _super);
    function CallbackIterResult(method, args, iterator) {
        var _this = _super.call(this, method, args) || this;
        _this.iterator = iterator;
        return _this;
    }
    CallbackIterResult.prototype.add = function (date) {
        if (this.iterator(date, this._result.length)) {
            this._result.push(date);
            return true;
        }
        return false;
    };
    return CallbackIterResult;
}(iterresult));
/* harmony default export */ var callbackiterresult = (callbackiterresult_CallbackIterResult);

// CONCATENATED MODULE: ./src/types.ts
var Frequency;
(function (Frequency) {
    Frequency[Frequency["YEARLY"] = 0] = "YEARLY";
    Frequency[Frequency["MONTHLY"] = 1] = "MONTHLY";
    Frequency[Frequency["WEEKLY"] = 2] = "WEEKLY";
    Frequency[Frequency["DAILY"] = 3] = "DAILY";
    Frequency[Frequency["HOURLY"] = 4] = "HOURLY";
    Frequency[Frequency["MINUTELY"] = 5] = "MINUTELY";
    Frequency[Frequency["SECONDLY"] = 6] = "SECONDLY";
})(Frequency || (Frequency = {}));
function freqIsDailyOrGreater(freq) {
    return freq < Frequency.HOURLY;
}

// EXTERNAL MODULE: ./src/weekday.ts
var weekday = __webpack_require__(2);

// CONCATENATED MODULE: ./src/datetime.ts




var Time = /** @class */ (function () {
    function Time(hour, minute, second, millisecond) {
        this.hour = hour;
        this.minute = minute;
        this.second = second;
        this.millisecond = millisecond || 0;
    }
    Time.prototype.getHours = function () {
        return this.hour;
    };
    Time.prototype.getMinutes = function () {
        return this.minute;
    };
    Time.prototype.getSeconds = function () {
        return this.second;
    };
    Time.prototype.getMilliseconds = function () {
        return this.millisecond;
    };
    Time.prototype.getTime = function () {
        return ((this.hour * 60 * 60 + this.minute * 60 + this.second) * 1000 +
            this.millisecond);
    };
    return Time;
}());

var datetime_DateTime = /** @class */ (function (_super) {
    __extends(DateTime, _super);
    function DateTime(year, month, day, hour, minute, second, millisecond) {
        var _this = _super.call(this, hour, minute, second, millisecond) || this;
        _this.year = year;
        _this.month = month;
        _this.day = day;
        return _this;
    }
    DateTime.fromDate = function (date) {
        return new this(date.getUTCFullYear(), date.getUTCMonth() + 1, date.getUTCDate(), date.getUTCHours(), date.getUTCMinutes(), date.getUTCSeconds(), date.valueOf() % 1000);
    };
    DateTime.prototype.getWeekday = function () {
        return dateutil_dateutil.getWeekday(new Date(this.getTime()));
    };
    DateTime.prototype.getTime = function () {
        return new Date(Date.UTC(this.year, this.month - 1, this.day, this.hour, this.minute, this.second, this.millisecond)).getTime();
    };
    DateTime.prototype.getDay = function () {
        return this.day;
    };
    DateTime.prototype.getMonth = function () {
        return this.month;
    };
    DateTime.prototype.getYear = function () {
        return this.year;
    };
    DateTime.prototype.addYears = function (years) {
        this.year += years;
    };
    DateTime.prototype.addMonths = function (months) {
        this.month += months;
        if (this.month > 12) {
            var yearDiv = Math.floor(this.month / 12);
            var monthMod = Object(helpers["j" /* pymod */])(this.month, 12);
            this.month = monthMod;
            this.year += yearDiv;
            if (this.month === 0) {
                this.month = 12;
                --this.year;
            }
        }
    };
    DateTime.prototype.addWeekly = function (days, wkst) {
        if (wkst > this.getWeekday()) {
            this.day += -(this.getWeekday() + 1 + (6 - wkst)) + days * 7;
        }
        else {
            this.day += -(this.getWeekday() - wkst) + days * 7;
        }
        this.fixDay();
    };
    DateTime.prototype.addDaily = function (days) {
        this.day += days;
        this.fixDay();
    };
    DateTime.prototype.addHours = function (hours, filtered, byhour) {
        if (filtered) {
            // Jump to one iteration before next day
            this.hour += Math.floor((23 - this.hour) / hours) * hours;
        }
        while (true) {
            this.hour += hours;
            var _a = Object(helpers["a" /* divmod */])(this.hour, 24), dayDiv = _a.div, hourMod = _a.mod;
            if (dayDiv) {
                this.hour = hourMod;
                this.addDaily(dayDiv);
            }
            if (Object(helpers["b" /* empty */])(byhour) || Object(helpers["c" /* includes */])(byhour, this.hour))
                break;
        }
    };
    DateTime.prototype.addMinutes = function (minutes, filtered, byhour, byminute) {
        if (filtered) {
            // Jump to one iteration before next day
            this.minute +=
                Math.floor((1439 - (this.hour * 60 + this.minute)) / minutes) * minutes;
        }
        while (true) {
            this.minute += minutes;
            var _a = Object(helpers["a" /* divmod */])(this.minute, 60), hourDiv = _a.div, minuteMod = _a.mod;
            if (hourDiv) {
                this.minute = minuteMod;
                this.addHours(hourDiv, false, byhour);
            }
            if ((Object(helpers["b" /* empty */])(byhour) || Object(helpers["c" /* includes */])(byhour, this.hour)) &&
                (Object(helpers["b" /* empty */])(byminute) || Object(helpers["c" /* includes */])(byminute, this.minute))) {
                break;
            }
        }
    };
    DateTime.prototype.addSeconds = function (seconds, filtered, byhour, byminute, bysecond) {
        if (filtered) {
            // Jump to one iteration before next day
            this.second +=
                Math.floor((86399 - (this.hour * 3600 + this.minute * 60 + this.second)) / seconds) * seconds;
        }
        while (true) {
            this.second += seconds;
            var _a = Object(helpers["a" /* divmod */])(this.second, 60), minuteDiv = _a.div, secondMod = _a.mod;
            if (minuteDiv) {
                this.second = secondMod;
                this.addMinutes(minuteDiv, false, byhour, byminute);
            }
            if ((Object(helpers["b" /* empty */])(byhour) || Object(helpers["c" /* includes */])(byhour, this.hour)) &&
                (Object(helpers["b" /* empty */])(byminute) || Object(helpers["c" /* includes */])(byminute, this.minute)) &&
                (Object(helpers["b" /* empty */])(bysecond) || Object(helpers["c" /* includes */])(bysecond, this.second))) {
                break;
            }
        }
    };
    DateTime.prototype.fixDay = function () {
        if (this.day <= 28) {
            return;
        }
        var daysinmonth = dateutil_dateutil.monthRange(this.year, this.month - 1)[1];
        if (this.day <= daysinmonth) {
            return;
        }
        while (this.day > daysinmonth) {
            this.day -= daysinmonth;
            ++this.month;
            if (this.month === 13) {
                this.month = 1;
                ++this.year;
                if (this.year > dateutil_dateutil.MAXYEAR) {
                    return;
                }
            }
            daysinmonth = dateutil_dateutil.monthRange(this.year, this.month - 1)[1];
        }
    };
    DateTime.prototype.add = function (options, filtered) {
        var freq = options.freq, interval = options.interval, wkst = options.wkst, byhour = options.byhour, byminute = options.byminute, bysecond = options.bysecond;
        switch (freq) {
            case Frequency.YEARLY: return this.addYears(interval);
            case Frequency.MONTHLY: return this.addMonths(interval);
            case Frequency.WEEKLY: return this.addWeekly(interval, wkst);
            case Frequency.DAILY: return this.addDaily(interval);
            case Frequency.HOURLY: return this.addHours(interval, filtered, byhour);
            case Frequency.MINUTELY: return this.addMinutes(interval, filtered, byhour, byminute);
            case Frequency.SECONDLY: return this.addSeconds(interval, filtered, byhour, byminute, bysecond);
        }
    };
    return DateTime;
}(Time));


// CONCATENATED MODULE: ./src/parseoptions.ts







function initializeOptions(options) {
    var invalid = [];
    var keys = Object.keys(options);
    // Shallow copy for options and origOptions and check for invalid
    for (var _i = 0, keys_1 = keys; _i < keys_1.length; _i++) {
        var key = keys_1[_i];
        if (!Object(helpers["c" /* includes */])(rrule_defaultKeys, key))
            invalid.push(key);
        if (src_dateutil.isDate(options[key]) && !src_dateutil.isValidDate(options[key]))
            invalid.push(key);
    }
    if (invalid.length) {
        throw new Error('Invalid options: ' + invalid.join(', '));
    }
    return __assign({}, options);
}
function parseOptions(options) {
    var opts = __assign(__assign({}, DEFAULT_OPTIONS), initializeOptions(options));
    if (Object(helpers["f" /* isPresent */])(opts.byeaster))
        opts.freq = src_rrule.YEARLY;
    if (!(Object(helpers["f" /* isPresent */])(opts.freq) && src_rrule.FREQUENCIES[opts.freq])) {
        throw new Error("Invalid frequency: " + opts.freq + " " + options.freq);
    }
    if (!opts.dtstart)
        opts.dtstart = new Date(new Date().setMilliseconds(0));
    if (!Object(helpers["f" /* isPresent */])(opts.wkst)) {
        opts.wkst = src_rrule.MO.weekday;
    }
    else if (Object(helpers["e" /* isNumber */])(opts.wkst)) {
        // cool, just keep it like that
    }
    else {
        opts.wkst = opts.wkst.weekday;
    }
    if (Object(helpers["f" /* isPresent */])(opts.bysetpos)) {
        if (Object(helpers["e" /* isNumber */])(opts.bysetpos))
            opts.bysetpos = [opts.bysetpos];
        for (var i = 0; i < opts.bysetpos.length; i++) {
            var v = opts.bysetpos[i];
            if (v === 0 || !(v >= -366 && v <= 366)) {
                throw new Error('bysetpos must be between 1 and 366,' + ' or between -366 and -1');
            }
        }
    }
    if (!(Boolean(opts.byweekno) ||
        Object(helpers["h" /* notEmpty */])(opts.byweekno) ||
        Object(helpers["h" /* notEmpty */])(opts.byyearday) ||
        Boolean(opts.bymonthday) ||
        Object(helpers["h" /* notEmpty */])(opts.bymonthday) ||
        Object(helpers["f" /* isPresent */])(opts.byweekday) ||
        Object(helpers["f" /* isPresent */])(opts.byeaster))) {
        switch (opts.freq) {
            case src_rrule.YEARLY:
                if (!opts.bymonth)
                    opts.bymonth = opts.dtstart.getUTCMonth() + 1;
                opts.bymonthday = opts.dtstart.getUTCDate();
                break;
            case src_rrule.MONTHLY:
                opts.bymonthday = opts.dtstart.getUTCDate();
                break;
            case src_rrule.WEEKLY:
                opts.byweekday = [src_dateutil.getWeekday(opts.dtstart)];
                break;
        }
    }
    // bymonth
    if (Object(helpers["f" /* isPresent */])(opts.bymonth) && !Object(helpers["d" /* isArray */])(opts.bymonth)) {
        opts.bymonth = [opts.bymonth];
    }
    // byyearday
    if (Object(helpers["f" /* isPresent */])(opts.byyearday) &&
        !Object(helpers["d" /* isArray */])(opts.byyearday) &&
        Object(helpers["e" /* isNumber */])(opts.byyearday)) {
        opts.byyearday = [opts.byyearday];
    }
    // bymonthday
    if (!Object(helpers["f" /* isPresent */])(opts.bymonthday)) {
        opts.bymonthday = [];
        opts.bynmonthday = [];
    }
    else if (Object(helpers["d" /* isArray */])(opts.bymonthday)) {
        var bymonthday = [];
        var bynmonthday = [];
        for (var i = 0; i < opts.bymonthday.length; i++) {
            var v = opts.bymonthday[i];
            if (v > 0) {
                bymonthday.push(v);
            }
            else if (v < 0) {
                bynmonthday.push(v);
            }
        }
        opts.bymonthday = bymonthday;
        opts.bynmonthday = bynmonthday;
    }
    else if (opts.bymonthday < 0) {
        opts.bynmonthday = [opts.bymonthday];
        opts.bymonthday = [];
    }
    else {
        opts.bynmonthday = [];
        opts.bymonthday = [opts.bymonthday];
    }
    // byweekno
    if (Object(helpers["f" /* isPresent */])(opts.byweekno) && !Object(helpers["d" /* isArray */])(opts.byweekno)) {
        opts.byweekno = [opts.byweekno];
    }
    // byweekday / bynweekday
    if (!Object(helpers["f" /* isPresent */])(opts.byweekday)) {
        opts.bynweekday = null;
    }
    else if (Object(helpers["e" /* isNumber */])(opts.byweekday)) {
        opts.byweekday = [opts.byweekday];
        opts.bynweekday = null;
    }
    else if (Object(helpers["g" /* isWeekdayStr */])(opts.byweekday)) {
        opts.byweekday = [weekday["b" /* Weekday */].fromStr(opts.byweekday).weekday];
        opts.bynweekday = null;
    }
    else if (opts.byweekday instanceof weekday["b" /* Weekday */]) {
        if (!opts.byweekday.n || opts.freq > src_rrule.MONTHLY) {
            opts.byweekday = [opts.byweekday.weekday];
            opts.bynweekday = null;
        }
        else {
            opts.bynweekday = [[opts.byweekday.weekday, opts.byweekday.n]];
            opts.byweekday = null;
        }
    }
    else {
        var byweekday = [];
        var bynweekday = [];
        for (var i = 0; i < opts.byweekday.length; i++) {
            var wday = opts.byweekday[i];
            if (Object(helpers["e" /* isNumber */])(wday)) {
                byweekday.push(wday);
                continue;
            }
            else if (Object(helpers["g" /* isWeekdayStr */])(wday)) {
                byweekday.push(weekday["b" /* Weekday */].fromStr(wday).weekday);
                continue;
            }
            if (!wday.n || opts.freq > src_rrule.MONTHLY) {
                byweekday.push(wday.weekday);
            }
            else {
                bynweekday.push([wday.weekday, wday.n]);
            }
        }
        opts.byweekday = Object(helpers["h" /* notEmpty */])(byweekday) ? byweekday : null;
        opts.bynweekday = Object(helpers["h" /* notEmpty */])(bynweekday) ? bynweekday : null;
    }
    // byhour
    if (!Object(helpers["f" /* isPresent */])(opts.byhour)) {
        opts.byhour =
            opts.freq < src_rrule.HOURLY ? [opts.dtstart.getUTCHours()] : null;
    }
    else if (Object(helpers["e" /* isNumber */])(opts.byhour)) {
        opts.byhour = [opts.byhour];
    }
    // byminute
    if (!Object(helpers["f" /* isPresent */])(opts.byminute)) {
        opts.byminute =
            opts.freq < src_rrule.MINUTELY ? [opts.dtstart.getUTCMinutes()] : null;
    }
    else if (Object(helpers["e" /* isNumber */])(opts.byminute)) {
        opts.byminute = [opts.byminute];
    }
    // bysecond
    if (!Object(helpers["f" /* isPresent */])(opts.bysecond)) {
        opts.bysecond =
            opts.freq < src_rrule.SECONDLY ? [opts.dtstart.getUTCSeconds()] : null;
    }
    else if (Object(helpers["e" /* isNumber */])(opts.bysecond)) {
        opts.bysecond = [opts.bysecond];
    }
    return { parsedOptions: opts };
}
function buildTimeset(opts) {
    var millisecondModulo = opts.dtstart.getTime() % 1000;
    if (!freqIsDailyOrGreater(opts.freq)) {
        return [];
    }
    var timeset = [];
    opts.byhour.forEach(function (hour) {
        opts.byminute.forEach(function (minute) {
            opts.bysecond.forEach(function (second) {
                timeset.push(new Time(hour, minute, second, millisecondModulo));
            });
        });
    });
    return timeset;
}

// CONCATENATED MODULE: ./src/parsestring.ts





function parseString(rfcString) {
    var options = rfcString.split('\n').map(parseLine).filter(function (x) { return x !== null; });
    return __assign(__assign({}, options[0]), options[1]);
}
function parseDtstart(line) {
    var options = {};
    var dtstartWithZone = /DTSTART(?:;TZID=([^:=]+?))?(?::|=)([^;\s]+)/i.exec(line);
    if (!dtstartWithZone) {
        return options;
    }
    var _ = dtstartWithZone[0], tzid = dtstartWithZone[1], dtstart = dtstartWithZone[2];
    if (tzid) {
        options.tzid = tzid;
    }
    options.dtstart = src_dateutil.untilStringToDate(dtstart);
    return options;
}
function parseLine(rfcString) {
    rfcString = rfcString.replace(/^\s+|\s+$/, '');
    if (!rfcString.length)
        return null;
    var header = /^([A-Z]+?)[:;]/.exec(rfcString.toUpperCase());
    if (!header) {
        return parseRrule(rfcString);
    }
    var _ = header[0], key = header[1];
    switch (key.toUpperCase()) {
        case 'RRULE':
        case 'EXRULE':
            return parseRrule(rfcString);
        case 'DTSTART':
            return parseDtstart(rfcString);
        default:
            throw new Error("Unsupported RFC prop " + key + " in " + rfcString);
    }
}
function parseRrule(line) {
    var strippedLine = line.replace(/^RRULE:/i, '');
    var options = parseDtstart(strippedLine);
    var attrs = line.replace(/^(?:RRULE|EXRULE):/i, '').split(';');
    attrs.forEach(function (attr) {
        var _a = attr.split('='), key = _a[0], value = _a[1];
        switch (key.toUpperCase()) {
            case 'FREQ':
                options.freq = Frequency[value.toUpperCase()];
                break;
            case 'WKST':
                options.wkst = Days[value.toUpperCase()];
                break;
            case 'COUNT':
            case 'INTERVAL':
            case 'BYSETPOS':
            case 'BYMONTH':
            case 'BYMONTHDAY':
            case 'BYYEARDAY':
            case 'BYWEEKNO':
            case 'BYHOUR':
            case 'BYMINUTE':
            case 'BYSECOND':
                var num = parseNumber(value);
                var optionKey = key.toLowerCase();
                // @ts-ignore
                options[optionKey] = num;
                break;
            case 'BYWEEKDAY':
            case 'BYDAY':
                options.byweekday = parseWeekday(value);
                break;
            case 'DTSTART':
            case 'TZID':
                // for backwards compatibility
                var dtstart = parseDtstart(line);
                options.tzid = dtstart.tzid;
                options.dtstart = dtstart.dtstart;
                break;
            case 'UNTIL':
                options.until = src_dateutil.untilStringToDate(value);
                break;
            case 'BYEASTER':
                options.byeaster = Number(value);
                break;
            default:
                throw new Error("Unknown RRULE property '" + key + "'");
        }
    });
    return options;
}
function parseNumber(value) {
    if (value.indexOf(',') !== -1) {
        var values = value.split(',');
        return values.map(parseIndividualNumber);
    }
    return parseIndividualNumber(value);
}
function parseIndividualNumber(value) {
    if (/^[+-]?\d+$/.test(value)) {
        return Number(value);
    }
    return value;
}
function parseWeekday(value) {
    var days = value.split(',');
    return days.map(function (day) {
        if (day.length === 2) {
            // MO, TU, ...
            return Days[day]; // wday instanceof Weekday
        }
        // -1MO, +3FR, 1SO, 13TU ...
        var parts = day.match(/^([+-]?\d{1,2})([A-Z]{2})$/);
        var n = Number(parts[1]);
        var wdaypart = parts[2];
        var wday = Days[wdaypart].weekday;
        return new weekday["b" /* Weekday */](wday, n);
    });
}

// CONCATENATED MODULE: ./src/fake-luxon.ts
var fake_luxon_DateTime = {
    fromJSDate: function () {
        throw new TypeError();
    }
};

// CONCATENATED MODULE: ./src/datewithzone.ts


var datewithzone_DateWithZone = /** @class */ (function () {
    function DateWithZone(date, tzid) {
        this.date = date;
        this.tzid = tzid;
    }
    Object.defineProperty(DateWithZone.prototype, "isUTC", {
        get: function () {
            return !this.tzid || this.tzid.toUpperCase() === 'UTC';
        },
        enumerable: true,
        configurable: true
    });
    DateWithZone.prototype.toString = function () {
        var datestr = src_dateutil.timeToUntilString(this.date.getTime(), this.isUTC);
        if (!this.isUTC) {
            return ";TZID=" + this.tzid + ":" + datestr;
        }
        return ":" + datestr;
    };
    DateWithZone.prototype.getTime = function () {
        return this.date.getTime();
    };
    DateWithZone.prototype.rezonedDate = function () {
        if (this.isUTC) {
            return this.date;
        }
        try {
            var datetime = fake_luxon_DateTime
                .fromJSDate(this.date);
            var rezoned = datetime.setZone(this.tzid, { keepLocalTime: true });
            return rezoned.toJSDate();
        }
        catch (e) {
            if (e instanceof TypeError) {
                console.error('Using TZID without Luxon available is unsupported. Returned times are in UTC, not the requested time zone');
            }
            return this.date;
        }
    };
    return DateWithZone;
}());


// CONCATENATED MODULE: ./src/optionstostring.ts





function optionsToString(options) {
    var rrule = [];
    var dtstart = '';
    var keys = Object.keys(options);
    var defaultKeys = Object.keys(DEFAULT_OPTIONS);
    for (var i = 0; i < keys.length; i++) {
        if (keys[i] === 'tzid')
            continue;
        if (!Object(helpers["c" /* includes */])(defaultKeys, keys[i]))
            continue;
        var key = keys[i].toUpperCase();
        var value = options[keys[i]];
        var outValue = '';
        if (!Object(helpers["f" /* isPresent */])(value) || (Object(helpers["d" /* isArray */])(value) && !value.length))
            continue;
        switch (key) {
            case 'FREQ':
                outValue = src_rrule.FREQUENCIES[options.freq];
                break;
            case 'WKST':
                if (Object(helpers["e" /* isNumber */])(value)) {
                    outValue = new weekday["b" /* Weekday */](value).toString();
                }
                else {
                    outValue = value.toString();
                }
                break;
            case 'BYWEEKDAY':
                /*
                NOTE: BYWEEKDAY is a special case.
                RRule() deconstructs the rule.options.byweekday array
                into an array of Weekday arguments.
                On the other hand, rule.origOptions is an array of Weekdays.
                We need to handle both cases here.
                It might be worth change RRule to keep the Weekdays.
      
                Also, BYWEEKDAY (used by RRule) vs. BYDAY (RFC)
      
                */
                key = 'BYDAY';
                outValue = Object(helpers["n" /* toArray */])(value).map(function (wday) {
                    if (wday instanceof weekday["b" /* Weekday */]) {
                        return wday;
                    }
                    if (Object(helpers["d" /* isArray */])(wday)) {
                        return new weekday["b" /* Weekday */](wday[0], wday[1]);
                    }
                    return new weekday["b" /* Weekday */](wday);
                }).toString();
                break;
            case 'DTSTART':
                dtstart = buildDtstart(value, options.tzid);
                break;
            case 'UNTIL':
                outValue = src_dateutil.timeToUntilString(value, !options.tzid);
                break;
            default:
                if (Object(helpers["d" /* isArray */])(value)) {
                    var strValues = [];
                    for (var j = 0; j < value.length; j++) {
                        strValues[j] = String(value[j]);
                    }
                    outValue = strValues.toString();
                }
                else {
                    outValue = String(value);
                }
        }
        if (outValue) {
            rrule.push([key, outValue]);
        }
    }
    var rules = rrule.map(function (_a) {
        var key = _a[0], value = _a[1];
        return key + "=" + value.toString();
    }).join(';');
    var ruleString = '';
    if (rules !== '') {
        ruleString = "RRULE:" + rules;
    }
    return [dtstart, ruleString].filter(function (x) { return !!x; }).join('\n');
}
function buildDtstart(dtstart, tzid) {
    if (!dtstart) {
        return '';
    }
    return 'DTSTART' + new datewithzone_DateWithZone(new Date(dtstart), tzid).toString();
}

// CONCATENATED MODULE: ./src/cache.ts



var cache_Cache = /** @class */ (function () {
    function Cache() {
        this.all = false;
        this.before = [];
        this.after = [];
        this.between = [];
    }
    /**
     * @param {String} what - all/before/after/between
     * @param {Array,Date} value - an array of dates, one date, or null
     * @param {Object?} args - _iter arguments
     */
    Cache.prototype._cacheAdd = function (what, value, args) {
        if (value) {
            value =
                value instanceof Date
                    ? src_dateutil.clone(value)
                    : src_dateutil.cloneDates(value);
        }
        if (what === 'all') {
            this.all = value;
        }
        else {
            args._value = value;
            this[what].push(args);
        }
    };
    /**
     * @return false - not in the cache
     *         null  - cached, but zero occurrences (before/after)
     *         Date  - cached (before/after)
     *         []    - cached, but zero occurrences (all/between)
     *         [Date1, DateN] - cached (all/between)
     */
    Cache.prototype._cacheGet = function (what, args) {
        var cached = false;
        var argsKeys = args ? Object.keys(args) : [];
        var findCacheDiff = function (item) {
            for (var i = 0; i < argsKeys.length; i++) {
                var key = argsKeys[i];
                if (String(args[key]) !== String(item[key])) {
                    return true;
                }
            }
            return false;
        };
        var cachedObject = this[what];
        if (what === 'all') {
            cached = this.all;
        }
        else if (Object(helpers["d" /* isArray */])(cachedObject)) {
            // Let's see whether we've already called the
            // 'what' method with the same 'args'
            for (var i = 0; i < cachedObject.length; i++) {
                var item = cachedObject[i];
                if (argsKeys.length && findCacheDiff(item))
                    continue;
                cached = item._value;
                break;
            }
        }
        if (!cached && this.all) {
            // Not in the cache, but we already know all the occurrences,
            // so we can find the correct dates from the cached ones.
            var iterResult = new iterresult(what, args);
            for (var i = 0; i < this.all.length; i++) {
                if (!iterResult.accept(this.all[i]))
                    break;
            }
            cached = iterResult.getValue();
            this._cacheAdd(what, cached, args);
        }
        return Object(helpers["d" /* isArray */])(cached)
            ? src_dateutil.cloneDates(cached)
            : cached instanceof Date
                ? src_dateutil.clone(cached)
                : cached;
    };
    return Cache;
}());


// CONCATENATED MODULE: ./src/masks.ts


// =============================================================================
// Date masks
// =============================================================================
// Every mask is 7 days longer to handle cross-year weekly periods.
var M365MASK = __spreadArrays(Object(helpers["l" /* repeat */])(1, 31), Object(helpers["l" /* repeat */])(2, 28), Object(helpers["l" /* repeat */])(3, 31), Object(helpers["l" /* repeat */])(4, 30), Object(helpers["l" /* repeat */])(5, 31), Object(helpers["l" /* repeat */])(6, 30), Object(helpers["l" /* repeat */])(7, 31), Object(helpers["l" /* repeat */])(8, 31), Object(helpers["l" /* repeat */])(9, 30), Object(helpers["l" /* repeat */])(10, 31), Object(helpers["l" /* repeat */])(11, 30), Object(helpers["l" /* repeat */])(12, 31), Object(helpers["l" /* repeat */])(1, 7));
var M366MASK = __spreadArrays(Object(helpers["l" /* repeat */])(1, 31), Object(helpers["l" /* repeat */])(2, 29), Object(helpers["l" /* repeat */])(3, 31), Object(helpers["l" /* repeat */])(4, 30), Object(helpers["l" /* repeat */])(5, 31), Object(helpers["l" /* repeat */])(6, 30), Object(helpers["l" /* repeat */])(7, 31), Object(helpers["l" /* repeat */])(8, 31), Object(helpers["l" /* repeat */])(9, 30), Object(helpers["l" /* repeat */])(10, 31), Object(helpers["l" /* repeat */])(11, 30), Object(helpers["l" /* repeat */])(12, 31), Object(helpers["l" /* repeat */])(1, 7));
var M28 = Object(helpers["k" /* range */])(1, 29);
var M29 = Object(helpers["k" /* range */])(1, 30);
var M30 = Object(helpers["k" /* range */])(1, 31);
var M31 = Object(helpers["k" /* range */])(1, 32);
var MDAY366MASK = __spreadArrays(M31, M29, M31, M30, M31, M30, M31, M31, M30, M31, M30, M31, M31.slice(0, 7));
var MDAY365MASK = __spreadArrays(M31, M28, M31, M30, M31, M30, M31, M31, M30, M31, M30, M31, M31.slice(0, 7));
var NM28 = Object(helpers["k" /* range */])(-28, 0);
var NM29 = Object(helpers["k" /* range */])(-29, 0);
var NM30 = Object(helpers["k" /* range */])(-30, 0);
var NM31 = Object(helpers["k" /* range */])(-31, 0);
var NMDAY366MASK = __spreadArrays(NM31, NM29, NM31, NM30, NM31, NM30, NM31, NM31, NM30, NM31, NM30, NM31, NM31.slice(0, 7));
var NMDAY365MASK = __spreadArrays(NM31, NM28, NM31, NM30, NM31, NM30, NM31, NM31, NM30, NM31, NM30, NM31, NM31.slice(0, 7));
var M366RANGE = [0, 31, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335, 366];
var M365RANGE = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334, 365];
var WDAYMASK = (function () {
    var wdaymask = [];
    for (var i = 0; i < 55; i++)
        wdaymask = wdaymask.concat(Object(helpers["k" /* range */])(7));
    return wdaymask;
})();


// CONCATENATED MODULE: ./src/iterinfo/yearinfo.ts




function rebuildYear(year, options) {
    var firstyday = new Date(Date.UTC(year, 0, 1));
    var yearlen = src_dateutil.isLeapYear(year) ? 366 : 365;
    var nextyearlen = src_dateutil.isLeapYear(year + 1) ? 366 : 365;
    var yearordinal = src_dateutil.toOrdinal(firstyday);
    var yearweekday = src_dateutil.getWeekday(firstyday);
    var result = __assign(__assign({ yearlen: yearlen,
        nextyearlen: nextyearlen,
        yearordinal: yearordinal,
        yearweekday: yearweekday }, baseYearMasks(year)), { wnomask: null });
    if (Object(helpers["b" /* empty */])(options.byweekno)) {
        return result;
    }
    result.wnomask = Object(helpers["l" /* repeat */])(0, yearlen + 7);
    var firstwkst;
    var wyearlen;
    var no1wkst = firstwkst = Object(helpers["j" /* pymod */])(7 - yearweekday + options.wkst, 7);
    if (no1wkst >= 4) {
        no1wkst = 0;
        // Number of days in the year, plus the days we got
        // from last year.
        wyearlen =
            result.yearlen + Object(helpers["j" /* pymod */])(yearweekday - options.wkst, 7);
    }
    else {
        // Number of days in the year, minus the days we
        // left in last year.
        wyearlen = yearlen - no1wkst;
    }
    var div = Math.floor(wyearlen / 7);
    var mod = Object(helpers["j" /* pymod */])(wyearlen, 7);
    var numweeks = Math.floor(div + mod / 4);
    for (var j = 0; j < options.byweekno.length; j++) {
        var n = options.byweekno[j];
        if (n < 0) {
            n += numweeks + 1;
        }
        if (!(n > 0 && n <= numweeks)) {
            continue;
        }
        var i = void 0;
        if (n > 1) {
            i = no1wkst + (n - 1) * 7;
            if (no1wkst !== firstwkst) {
                i -= 7 - firstwkst;
            }
        }
        else {
            i = no1wkst;
        }
        for (var k = 0; k < 7; k++) {
            result.wnomask[i] = 1;
            i++;
            if (result.wdaymask[i] === options.wkst)
                break;
        }
    }
    if (Object(helpers["c" /* includes */])(options.byweekno, 1)) {
        // Check week number 1 of next year as well
        // orig-TODO : Check -numweeks for next year.
        var i = no1wkst + numweeks * 7;
        if (no1wkst !== firstwkst)
            i -= 7 - firstwkst;
        if (i < yearlen) {
            // If week starts in next year, we
            // don't care about it.
            for (var j = 0; j < 7; j++) {
                result.wnomask[i] = 1;
                i += 1;
                if (result.wdaymask[i] === options.wkst)
                    break;
            }
        }
    }
    if (no1wkst) {
        // Check last week number of last year as
        // well. If no1wkst is 0, either the year
        // started on week start, or week number 1
        // got days from last year, so there are no
        // days from last year's last week number in
        // this year.
        var lnumweeks = void 0;
        if (!Object(helpers["c" /* includes */])(options.byweekno, -1)) {
            var lyearweekday = src_dateutil.getWeekday(new Date(Date.UTC(year - 1, 0, 1)));
            var lno1wkst = Object(helpers["j" /* pymod */])(7 - lyearweekday.valueOf() + options.wkst, 7);
            var lyearlen = src_dateutil.isLeapYear(year - 1) ? 366 : 365;
            var weekst = void 0;
            if (lno1wkst >= 4) {
                lno1wkst = 0;
                weekst = lyearlen + Object(helpers["j" /* pymod */])(lyearweekday - options.wkst, 7);
            }
            else {
                weekst = yearlen - no1wkst;
            }
            lnumweeks = Math.floor(52 + Object(helpers["j" /* pymod */])(weekst, 7) / 4);
        }
        else {
            lnumweeks = -1;
        }
        if (Object(helpers["c" /* includes */])(options.byweekno, lnumweeks)) {
            for (var i = 0; i < no1wkst; i++)
                result.wnomask[i] = 1;
        }
    }
    return result;
}
function baseYearMasks(year) {
    var yearlen = src_dateutil.isLeapYear(year) ? 366 : 365;
    var firstyday = new Date(Date.UTC(year, 0, 1));
    var wday = src_dateutil.getWeekday(firstyday);
    if (yearlen === 365) {
        return {
            mmask: M365MASK,
            mdaymask: MDAY365MASK,
            nmdaymask: NMDAY365MASK,
            wdaymask: WDAYMASK.slice(wday),
            mrange: M365RANGE
        };
    }
    return {
        mmask: M366MASK,
        mdaymask: MDAY366MASK,
        nmdaymask: NMDAY366MASK,
        wdaymask: WDAYMASK.slice(wday),
        mrange: M366RANGE
    };
}

// CONCATENATED MODULE: ./src/iterinfo/monthinfo.ts


function rebuildMonth(year, month, yearlen, mrange, wdaymask, options) {
    var result = {
        lastyear: year,
        lastmonth: month,
        nwdaymask: []
    };
    var ranges = [];
    if (options.freq === src_rrule.YEARLY) {
        if (Object(helpers["b" /* empty */])(options.bymonth)) {
            ranges = [[0, yearlen]];
        }
        else {
            for (var j = 0; j < options.bymonth.length; j++) {
                month = options.bymonth[j];
                ranges.push(mrange.slice(month - 1, month + 1));
            }
        }
    }
    else if (options.freq === src_rrule.MONTHLY) {
        ranges = [mrange.slice(month - 1, month + 1)];
    }
    if (Object(helpers["b" /* empty */])(ranges)) {
        return result;
    }
    // Weekly frequency won't get here, so we may not
    // care about cross-year weekly periods.
    result.nwdaymask = Object(helpers["l" /* repeat */])(0, yearlen);
    for (var j = 0; j < ranges.length; j++) {
        var rang = ranges[j];
        var first = rang[0];
        var last = rang[1] - 1;
        for (var k = 0; k < options.bynweekday.length; k++) {
            var i = void 0;
            var _a = options.bynweekday[k], wday = _a[0], n = _a[1];
            if (n < 0) {
                i = last + (n + 1) * 7;
                i -= Object(helpers["j" /* pymod */])(wdaymask[i] - wday, 7);
            }
            else {
                i = first + (n - 1) * 7;
                i += Object(helpers["j" /* pymod */])(7 - wdaymask[i] + wday, 7);
            }
            if (first <= i && i <= last)
                result.nwdaymask[i] = 1;
        }
    }
    return result;
}

// CONCATENATED MODULE: ./src/iterinfo/easter.ts
function easter(y, offset) {
    if (offset === void 0) { offset = 0; }
    var a = y % 19;
    var b = Math.floor(y / 100);
    var c = y % 100;
    var d = Math.floor(b / 4);
    var e = b % 4;
    var f = Math.floor((b + 8) / 25);
    var g = Math.floor((b - f + 1) / 3);
    var h = Math.floor(19 * a + b - d - g + 15) % 30;
    var i = Math.floor(c / 4);
    var k = c % 4;
    var l = Math.floor(32 + 2 * e + 2 * i - h - k) % 7;
    var m = Math.floor((a + 11 * h + 22 * l) / 451);
    var month = Math.floor((h + l - 7 * m + 114) / 31);
    var day = ((h + l - 7 * m + 114) % 31) + 1;
    var date = Date.UTC(y, month - 1, day + offset);
    var yearStart = Date.UTC(y, 0, 1);
    return [Math.ceil((date - yearStart) / (1000 * 60 * 60 * 24))];
}

// CONCATENATED MODULE: ./src/iterinfo/index.ts







// =============================================================================
// Iterinfo
// =============================================================================
var iterinfo_Iterinfo = /** @class */ (function () {
    function Iterinfo(options) {
        this.options = options;
    }
    Iterinfo.prototype.rebuild = function (year, month) {
        var options = this.options;
        if (year !== this.lastyear) {
            this.yearinfo = rebuildYear(year, options);
        }
        if (Object(helpers["h" /* notEmpty */])(options.bynweekday) &&
            (month !== this.lastmonth || year !== this.lastyear)) {
            var _a = this.yearinfo, yearlen = _a.yearlen, mrange = _a.mrange, wdaymask = _a.wdaymask;
            this.monthinfo = rebuildMonth(year, month, yearlen, mrange, wdaymask, options);
        }
        if (Object(helpers["f" /* isPresent */])(options.byeaster)) {
            this.eastermask = easter(year, options.byeaster);
        }
    };
    Object.defineProperty(Iterinfo.prototype, "lastyear", {
        get: function () {
            return this.monthinfo ? this.monthinfo.lastyear : null;
        },
        enumerable: true,
        configurable: true
    });
    Object.defineProperty(Iterinfo.prototype, "lastmonth", {
        get: function () {
            return this.monthinfo ? this.monthinfo.lastmonth : null;
        },
        enumerable: true,
        configurable: true
    });
    Object.defineProperty(Iterinfo.prototype, "yearlen", {
        get: function () {
            return this.yearinfo.yearlen;
        },
        enumerable: true,
        configurable: true
    });
    Object.defineProperty(Iterinfo.prototype, "yearordinal", {
        get: function () {
            return this.yearinfo.yearordinal;
        },
        enumerable: true,
        configurable: true
    });
    Object.defineProperty(Iterinfo.prototype, "mrange", {
        get: function () {
            return this.yearinfo.mrange;
        },
        enumerable: true,
        configurable: true
    });
    Object.defineProperty(Iterinfo.prototype, "wdaymask", {
        get: function () {
            return this.yearinfo.wdaymask;
        },
        enumerable: true,
        configurable: true
    });
    Object.defineProperty(Iterinfo.prototype, "mmask", {
        get: function () {
            return this.yearinfo.mmask;
        },
        enumerable: true,
        configurable: true
    });
    Object.defineProperty(Iterinfo.prototype, "wnomask", {
        get: function () {
            return this.yearinfo.wnomask;
        },
        enumerable: true,
        configurable: true
    });
    Object.defineProperty(Iterinfo.prototype, "nwdaymask", {
        get: function () {
            return this.monthinfo ? this.monthinfo.nwdaymask : [];
        },
        enumerable: true,
        configurable: true
    });
    Object.defineProperty(Iterinfo.prototype, "nextyearlen", {
        get: function () {
            return this.yearinfo.nextyearlen;
        },
        enumerable: true,
        configurable: true
    });
    Object.defineProperty(Iterinfo.prototype, "mdaymask", {
        get: function () {
            return this.yearinfo.mdaymask;
        },
        enumerable: true,
        configurable: true
    });
    Object.defineProperty(Iterinfo.prototype, "nmdaymask", {
        get: function () {
            return this.yearinfo.nmdaymask;
        },
        enumerable: true,
        configurable: true
    });
    Iterinfo.prototype.ydayset = function () {
        return [Object(helpers["k" /* range */])(this.yearlen), 0, this.yearlen];
    };
    Iterinfo.prototype.mdayset = function (_, month, __) {
        var start = this.mrange[month - 1];
        var end = this.mrange[month];
        var set = Object(helpers["l" /* repeat */])(null, this.yearlen);
        for (var i = start; i < end; i++)
            set[i] = i;
        return [set, start, end];
    };
    Iterinfo.prototype.wdayset = function (year, month, day) {
        // We need to handle cross-year weeks here.
        var set = Object(helpers["l" /* repeat */])(null, this.yearlen + 7);
        var i = src_dateutil.toOrdinal(new Date(Date.UTC(year, month - 1, day))) -
            this.yearordinal;
        var start = i;
        for (var j = 0; j < 7; j++) {
            set[i] = i;
            ++i;
            if (this.wdaymask[i] === this.options.wkst)
                break;
        }
        return [set, start, i];
    };
    Iterinfo.prototype.ddayset = function (year, month, day) {
        var set = Object(helpers["l" /* repeat */])(null, this.yearlen);
        var i = src_dateutil.toOrdinal(new Date(Date.UTC(year, month - 1, day))) -
            this.yearordinal;
        set[i] = i;
        return [set, i, i + 1];
    };
    Iterinfo.prototype.htimeset = function (hour, _, second, millisecond) {
        var _this = this;
        var set = [];
        this.options.byminute.forEach(function (minute) {
            set = set.concat(_this.mtimeset(hour, minute, second, millisecond));
        });
        src_dateutil.sort(set);
        return set;
    };
    Iterinfo.prototype.mtimeset = function (hour, minute, _, millisecond) {
        var set = this.options.bysecond.map(function (second) {
            return new Time(hour, minute, second, millisecond);
        });
        src_dateutil.sort(set);
        return set;
    };
    Iterinfo.prototype.stimeset = function (hour, minute, second, millisecond) {
        return [new Time(hour, minute, second, millisecond)];
    };
    Iterinfo.prototype.getdayset = function (freq) {
        switch (freq) {
            case Frequency.YEARLY: return this.ydayset.bind(this);
            case Frequency.MONTHLY: return this.mdayset.bind(this);
            case Frequency.WEEKLY: return this.wdayset.bind(this);
            case Frequency.DAILY: return this.ddayset.bind(this);
            default: return this.ddayset.bind(this);
        }
    };
    Iterinfo.prototype.gettimeset = function (freq) {
        switch (freq) {
            case Frequency.HOURLY: return this.htimeset.bind(this);
            case Frequency.MINUTELY: return this.mtimeset.bind(this);
            case Frequency.SECONDLY: return this.stimeset.bind(this);
        }
    };
    return Iterinfo;
}());
/* harmony default export */ var iterinfo = (iterinfo_Iterinfo);

// CONCATENATED MODULE: ./src/iter/poslist.ts


function buildPoslist(bysetpos, timeset, start, end, ii, dayset) {
    var poslist = [];
    for (var j = 0; j < bysetpos.length; j++) {
        var daypos = void 0;
        var timepos = void 0;
        var pos = bysetpos[j];
        if (pos < 0) {
            daypos = Math.floor(pos / timeset.length);
            timepos = Object(helpers["j" /* pymod */])(pos, timeset.length);
        }
        else {
            daypos = Math.floor((pos - 1) / timeset.length);
            timepos = Object(helpers["j" /* pymod */])(pos - 1, timeset.length);
        }
        var tmp = [];
        for (var k = start; k < end; k++) {
            var val = dayset[k];
            if (!Object(helpers["f" /* isPresent */])(val))
                continue;
            tmp.push(val);
        }
        var i = void 0;
        if (daypos < 0) {
            i = tmp.slice(daypos)[0];
        }
        else {
            i = tmp[daypos];
        }
        var time = timeset[timepos];
        var date = src_dateutil.fromOrdinal(ii.yearordinal + i);
        var res = src_dateutil.combine(date, time);
        // XXX: can this ever be in the array?
        // - compare the actual date instead?
        if (!Object(helpers["c" /* includes */])(poslist, res))
            poslist.push(res);
    }
    src_dateutil.sort(poslist);
    return poslist;
}

// CONCATENATED MODULE: ./src/iter/index.ts









function iter(iterResult, options) {
    var dtstart = options.dtstart, freq = options.freq, interval = options.interval, until = options.until, bysetpos = options.bysetpos;
    var count = options.count;
    if (count === 0 || interval === 0) {
        return emitResult(iterResult);
    }
    var counterDate = datetime_DateTime.fromDate(dtstart);
    var ii = new iterinfo(options);
    ii.rebuild(counterDate.year, counterDate.month);
    var timeset = makeTimeset(ii, counterDate, options);
    while (true) {
        var _a = ii.getdayset(freq)(counterDate.year, counterDate.month, counterDate.day), dayset = _a[0], start = _a[1], end = _a[2];
        var filtered = removeFilteredDays(dayset, start, end, ii, options);
        if (Object(helpers["h" /* notEmpty */])(bysetpos)) {
            var poslist = buildPoslist(bysetpos, timeset, start, end, ii, dayset);
            for (var j = 0; j < poslist.length; j++) {
                var res = poslist[j];
                if (until && res > until) {
                    return emitResult(iterResult);
                }
                if (res >= dtstart) {
                    var rezonedDate = rezoneIfNeeded(res, options);
                    if (!iterResult.accept(rezonedDate)) {
                        return emitResult(iterResult);
                    }
                    if (count) {
                        --count;
                        if (!count) {
                            return emitResult(iterResult);
                        }
                    }
                }
            }
        }
        else {
            for (var j = start; j < end; j++) {
                var currentDay = dayset[j];
                if (!Object(helpers["f" /* isPresent */])(currentDay)) {
                    continue;
                }
                var date = src_dateutil.fromOrdinal(ii.yearordinal + currentDay);
                for (var k = 0; k < timeset.length; k++) {
                    var time = timeset[k];
                    var res = src_dateutil.combine(date, time);
                    if (until && res > until) {
                        return emitResult(iterResult);
                    }
                    if (res >= dtstart) {
                        var rezonedDate = rezoneIfNeeded(res, options);
                        if (!iterResult.accept(rezonedDate)) {
                            return emitResult(iterResult);
                        }
                        if (count) {
                            --count;
                            if (!count) {
                                return emitResult(iterResult);
                            }
                        }
                    }
                }
            }
        }
        if (options.interval === 0) {
            return emitResult(iterResult);
        }
        // Handle frequency and interval
        counterDate.add(options, filtered);
        if (counterDate.year > src_dateutil.MAXYEAR) {
            return emitResult(iterResult);
        }
        if (!freqIsDailyOrGreater(freq)) {
            timeset = ii.gettimeset(freq)(counterDate.hour, counterDate.minute, counterDate.second, 0);
        }
        ii.rebuild(counterDate.year, counterDate.month);
    }
}
function isFiltered(ii, currentDay, options) {
    var bymonth = options.bymonth, byweekno = options.byweekno, byweekday = options.byweekday, byeaster = options.byeaster, bymonthday = options.bymonthday, bynmonthday = options.bynmonthday, byyearday = options.byyearday;
    return ((Object(helpers["h" /* notEmpty */])(bymonth) && !Object(helpers["c" /* includes */])(bymonth, ii.mmask[currentDay])) ||
        (Object(helpers["h" /* notEmpty */])(byweekno) && !ii.wnomask[currentDay]) ||
        (Object(helpers["h" /* notEmpty */])(byweekday) && !Object(helpers["c" /* includes */])(byweekday, ii.wdaymask[currentDay])) ||
        (Object(helpers["h" /* notEmpty */])(ii.nwdaymask) && !ii.nwdaymask[currentDay]) ||
        (byeaster !== null && !Object(helpers["c" /* includes */])(ii.eastermask, currentDay)) ||
        ((Object(helpers["h" /* notEmpty */])(bymonthday) || Object(helpers["h" /* notEmpty */])(bynmonthday)) &&
            !Object(helpers["c" /* includes */])(bymonthday, ii.mdaymask[currentDay]) &&
            !Object(helpers["c" /* includes */])(bynmonthday, ii.nmdaymask[currentDay])) ||
        (Object(helpers["h" /* notEmpty */])(byyearday) &&
            ((currentDay < ii.yearlen &&
                !Object(helpers["c" /* includes */])(byyearday, currentDay + 1) &&
                !Object(helpers["c" /* includes */])(byyearday, -ii.yearlen + currentDay)) ||
                (currentDay >= ii.yearlen &&
                    !Object(helpers["c" /* includes */])(byyearday, currentDay + 1 - ii.yearlen) &&
                    !Object(helpers["c" /* includes */])(byyearday, -ii.nextyearlen + currentDay - ii.yearlen)))));
}
function rezoneIfNeeded(date, options) {
    return new datewithzone_DateWithZone(date, options.tzid).rezonedDate();
}
function emitResult(iterResult) {
    return iterResult.getValue();
}
function removeFilteredDays(dayset, start, end, ii, options) {
    var filtered = false;
    for (var dayCounter = start; dayCounter < end; dayCounter++) {
        var currentDay = dayset[dayCounter];
        filtered = isFiltered(ii, currentDay, options);
        if (filtered)
            dayset[currentDay] = null;
    }
    return filtered;
}
function makeTimeset(ii, counterDate, options) {
    var freq = options.freq, byhour = options.byhour, byminute = options.byminute, bysecond = options.bysecond;
    if (freqIsDailyOrGreater(freq)) {
        return buildTimeset(options);
    }
    if ((freq >= src_rrule.HOURLY &&
        Object(helpers["h" /* notEmpty */])(byhour) &&
        !Object(helpers["c" /* includes */])(byhour, counterDate.hour)) ||
        (freq >= src_rrule.MINUTELY &&
            Object(helpers["h" /* notEmpty */])(byminute) &&
            !Object(helpers["c" /* includes */])(byminute, counterDate.minute)) ||
        (freq >= src_rrule.SECONDLY &&
            Object(helpers["h" /* notEmpty */])(bysecond) &&
            !Object(helpers["c" /* includes */])(bysecond, counterDate.second))) {
        return [];
    }
    return ii.gettimeset(freq)(counterDate.hour, counterDate.minute, counterDate.second, counterDate.millisecond);
}

// CONCATENATED MODULE: ./src/rrule.ts










var getnlp = function () {
    // Lazy, runtime import to avoid circular refs.
    if (!getnlp._nlp) {
        getnlp._nlp = __webpack_require__(3);
    }
    return getnlp._nlp;
};
// =============================================================================
// RRule
// =============================================================================
var Days = {
    MO: new weekday["b" /* Weekday */](0),
    TU: new weekday["b" /* Weekday */](1),
    WE: new weekday["b" /* Weekday */](2),
    TH: new weekday["b" /* Weekday */](3),
    FR: new weekday["b" /* Weekday */](4),
    SA: new weekday["b" /* Weekday */](5),
    SU: new weekday["b" /* Weekday */](6)
};
var DEFAULT_OPTIONS = {
    freq: Frequency.YEARLY,
    dtstart: null,
    interval: 1,
    wkst: Days.MO,
    count: null,
    until: null,
    tzid: null,
    bysetpos: null,
    bymonth: null,
    bymonthday: null,
    bynmonthday: null,
    byyearday: null,
    byweekno: null,
    byweekday: null,
    bynweekday: null,
    byhour: null,
    byminute: null,
    bysecond: null,
    byeaster: null
};
var rrule_defaultKeys = Object.keys(DEFAULT_OPTIONS);
/**
 *
 * @param {Options?} options - see <http://labix.org/python-dateutil/#head-cf004ee9a75592797e076752b2a889c10f445418>
 *        The only required option is `freq`, one of RRule.YEARLY, RRule.MONTHLY, ...
 * @constructor
 */
var rrule_RRule = /** @class */ (function () {
    function RRule(options, noCache) {
        if (options === void 0) { options = {}; }
        if (noCache === void 0) { noCache = false; }
        // RFC string
        this._cache = noCache ? null : new cache_Cache();
        // used by toString()
        this.origOptions = initializeOptions(options);
        var parsedOptions = parseOptions(options).parsedOptions;
        this.options = parsedOptions;
    }
    RRule.parseText = function (text, language) {
        return getnlp().parseText(text, language);
    };
    RRule.fromText = function (text, language) {
        return getnlp().fromText(text, language);
    };
    RRule.fromString = function (str) {
        return new RRule(RRule.parseString(str) || undefined);
    };
    RRule.prototype._iter = function (iterResult) {
        return iter(iterResult, this.options);
    };
    RRule.prototype._cacheGet = function (what, args) {
        if (!this._cache)
            return false;
        return this._cache._cacheGet(what, args);
    };
    RRule.prototype._cacheAdd = function (what, value, args) {
        if (!this._cache)
            return;
        return this._cache._cacheAdd(what, value, args);
    };
    /**
     * @param {Function} iterator - optional function that will be called
     *                   on each date that is added. It can return false
     *                   to stop the iteration.
     * @return Array containing all recurrences.
     */
    RRule.prototype.all = function (iterator) {
        if (iterator) {
            return this._iter(new callbackiterresult('all', {}, iterator));
        }
        var result = this._cacheGet('all');
        if (result === false) {
            result = this._iter(new iterresult('all', {}));
            this._cacheAdd('all', result);
        }
        return result;
    };
    /**
     * Returns all the occurrences of the rrule between after and before.
     * The inc keyword defines what happens if after and/or before are
     * themselves occurrences. With inc == True, they will be included in the
     * list, if they are found in the recurrence set.
     * @return Array
     */
    RRule.prototype.between = function (after, before, inc, iterator) {
        if (inc === void 0) { inc = false; }
        if (!src_dateutil.isValidDate(after) || !src_dateutil.isValidDate(before))
            throw new Error('Invalid date passed in to RRule.between');
        var args = {
            before: before,
            after: after,
            inc: inc
        };
        if (iterator) {
            return this._iter(new callbackiterresult('between', args, iterator));
        }
        var result = this._cacheGet('between', args);
        if (result === false) {
            result = this._iter(new iterresult('between', args));
            this._cacheAdd('between', result, args);
        }
        return result;
    };
    /**
     * Returns the last recurrence before the given datetime instance.
     * The inc keyword defines what happens if dt is an occurrence.
     * With inc == True, if dt itself is an occurrence, it will be returned.
     * @return Date or null
     */
    RRule.prototype.before = function (dt, inc) {
        if (inc === void 0) { inc = false; }
        if (!src_dateutil.isValidDate(dt))
            throw new Error('Invalid date passed in to RRule.before');
        var args = { dt: dt, inc: inc };
        var result = this._cacheGet('before', args);
        if (result === false) {
            result = this._iter(new iterresult('before', args));
            this._cacheAdd('before', result, args);
        }
        return result;
    };
    /**
     * Returns the first recurrence after the given datetime instance.
     * The inc keyword defines what happens if dt is an occurrence.
     * With inc == True, if dt itself is an occurrence, it will be returned.
     * @return Date or null
     */
    RRule.prototype.after = function (dt, inc) {
        if (inc === void 0) { inc = false; }
        if (!src_dateutil.isValidDate(dt))
            throw new Error('Invalid date passed in to RRule.after');
        var args = { dt: dt, inc: inc };
        var result = this._cacheGet('after', args);
        if (result === false) {
            result = this._iter(new iterresult('after', args));
            this._cacheAdd('after', result, args);
        }
        return result;
    };
    /**
     * Returns the number of recurrences in this set. It will have go trough
     * the whole recurrence, if this hasn't been done before.
     */
    RRule.prototype.count = function () {
        return this.all().length;
    };
    /**
     * Converts the rrule into its string representation
     * @see <http://www.ietf.org/rfc/rfc2445.txt>
     * @return String
     */
    RRule.prototype.toString = function () {
        return optionsToString(this.origOptions);
    };
    /**
     * Will convert all rules described in nlp:ToText
     * to text.
     */
    RRule.prototype.toText = function (gettext, language, dateFormatter) {
        return getnlp().toText(this, gettext, language, dateFormatter);
    };
    RRule.prototype.isFullyConvertibleToText = function () {
        return getnlp().isFullyConvertible(this);
    };
    /**
     * @return a RRule instance with the same freq and options
     *          as this one (cache is not cloned)
     */
    RRule.prototype.clone = function () {
        return new RRule(this.origOptions);
    };
    // RRule class 'constants'
    RRule.FREQUENCIES = [
        'YEARLY',
        'MONTHLY',
        'WEEKLY',
        'DAILY',
        'HOURLY',
        'MINUTELY',
        'SECONDLY'
    ];
    RRule.YEARLY = Frequency.YEARLY;
    RRule.MONTHLY = Frequency.MONTHLY;
    RRule.WEEKLY = Frequency.WEEKLY;
    RRule.DAILY = Frequency.DAILY;
    RRule.HOURLY = Frequency.HOURLY;
    RRule.MINUTELY = Frequency.MINUTELY;
    RRule.SECONDLY = Frequency.SECONDLY;
    RRule.MO = Days.MO;
    RRule.TU = Days.TU;
    RRule.WE = Days.WE;
    RRule.TH = Days.TH;
    RRule.FR = Days.FR;
    RRule.SA = Days.SA;
    RRule.SU = Days.SU;
    RRule.parseString = parseString;
    RRule.optionsToString = optionsToString;
    return RRule;
}());
/* harmony default export */ var src_rrule = (rrule_RRule);

// CONCATENATED MODULE: ./src/iterset.ts



function iterSet(iterResult, _rrule, _exrule, _rdate, _exdate, tzid) {
    var _exdateHash = {};
    var _accept = iterResult.accept;
    function evalExdate(after, before) {
        _exrule.forEach(function (rrule) {
            rrule.between(after, before, true).forEach(function (date) {
                _exdateHash[Number(date)] = true;
            });
        });
    }
    _exdate.forEach(function (date) {
        var zonedDate = new datewithzone_DateWithZone(date, tzid).rezonedDate();
        _exdateHash[Number(zonedDate)] = true;
    });
    iterResult.accept = function (date) {
        var dt = Number(date);
        if (isNaN(dt))
            return _accept.call(this, date);
        if (!_exdateHash[dt]) {
            evalExdate(new Date(dt - 1), new Date(dt + 1));
            if (!_exdateHash[dt]) {
                _exdateHash[dt] = true;
                return _accept.call(this, date);
            }
        }
        return true;
    };
    if (iterResult.method === 'between') {
        evalExdate(iterResult.args.after, iterResult.args.before);
        iterResult.accept = function (date) {
            var dt = Number(date);
            if (!_exdateHash[dt]) {
                _exdateHash[dt] = true;
                return _accept.call(this, date);
            }
            return true;
        };
    }
    for (var i = 0; i < _rdate.length; i++) {
        var zonedDate = new datewithzone_DateWithZone(_rdate[i], tzid).rezonedDate();
        if (!iterResult.accept(new Date(zonedDate.getTime())))
            break;
    }
    _rrule.forEach(function (rrule) {
        iter(iterResult, rrule.options);
    });
    var res = iterResult._result;
    src_dateutil.sort(res);
    switch (iterResult.method) {
        case 'all':
        case 'between':
            return res;
        case 'before':
            return ((res.length && res[res.length - 1]) || null);
        case 'after':
        default:
            return ((res.length && res[0]) || null);
    }
}

// CONCATENATED MODULE: ./src/rrulestr.ts






/**
 * RRuleStr
 *  To parse a set of rrule strings
 */
var rrulestr_DEFAULT_OPTIONS = {
    dtstart: null,
    cache: false,
    unfold: false,
    forceset: false,
    compatible: false,
    tzid: null
};
function parseInput(s, options) {
    var rrulevals = [];
    var rdatevals = [];
    var exrulevals = [];
    var exdatevals = [];
    var _a = parseDtstart(s), dtstart = _a.dtstart, tzid = _a.tzid;
    var lines = splitIntoLines(s, options.unfold);
    lines.forEach(function (line) {
        if (!line)
            return;
        var _a = breakDownLine(line), name = _a.name, parms = _a.parms, value = _a.value;
        switch (name.toUpperCase()) {
            case 'RRULE':
                if (parms.length) {
                    throw new Error("unsupported RRULE parm: " + parms.join(','));
                }
                rrulevals.push(parseString(line));
                break;
            case 'RDATE':
                var _b = /RDATE(?:;TZID=([^:=]+))?/i.exec(line), _ = _b[0], rdateTzid = _b[1];
                if (rdateTzid && !tzid) {
                    tzid = rdateTzid;
                }
                rdatevals = rdatevals.concat(parseRDate(value, parms));
                break;
            case 'EXRULE':
                if (parms.length) {
                    throw new Error("unsupported EXRULE parm: " + parms.join(','));
                }
                exrulevals.push(parseString(value));
                break;
            case 'EXDATE':
                exdatevals = exdatevals.concat(parseRDate(value, parms));
                break;
            case 'DTSTART':
                break;
            default:
                throw new Error('unsupported property: ' + name);
        }
    });
    return {
        dtstart: dtstart,
        tzid: tzid,
        rrulevals: rrulevals,
        rdatevals: rdatevals,
        exrulevals: exrulevals,
        exdatevals: exdatevals
    };
}
function buildRule(s, options) {
    var _a = parseInput(s, options), rrulevals = _a.rrulevals, rdatevals = _a.rdatevals, exrulevals = _a.exrulevals, exdatevals = _a.exdatevals, dtstart = _a.dtstart, tzid = _a.tzid;
    var noCache = options.cache === false;
    if (options.compatible) {
        options.forceset = true;
        options.unfold = true;
    }
    if (options.forceset ||
        rrulevals.length > 1 ||
        rdatevals.length ||
        exrulevals.length ||
        exdatevals.length) {
        var rset_1 = new rruleset(noCache);
        rset_1.dtstart(dtstart);
        rset_1.tzid(tzid || undefined);
        rrulevals.forEach(function (val) {
            rset_1.rrule(new src_rrule(groomRruleOptions(val, dtstart, tzid), noCache));
        });
        rdatevals.forEach(function (date) {
            rset_1.rdate(date);
        });
        exrulevals.forEach(function (val) {
            rset_1.exrule(new src_rrule(groomRruleOptions(val, dtstart, tzid), noCache));
        });
        exdatevals.forEach(function (date) {
            rset_1.exdate(date);
        });
        if (options.compatible && options.dtstart)
            rset_1.rdate(dtstart);
        return rset_1;
    }
    var val = rrulevals[0] || {};
    return new src_rrule(groomRruleOptions(val, val.dtstart || options.dtstart || dtstart, val.tzid || options.tzid || tzid), noCache);
}
function rrulestr(s, options) {
    if (options === void 0) { options = {}; }
    return buildRule(s, rrulestr_initializeOptions(options));
}
function groomRruleOptions(val, dtstart, tzid) {
    return __assign(__assign({}, val), { dtstart: dtstart,
        tzid: tzid });
}
function rrulestr_initializeOptions(options) {
    var invalid = [];
    var keys = Object.keys(options);
    var defaultKeys = Object.keys(rrulestr_DEFAULT_OPTIONS);
    keys.forEach(function (key) {
        if (!Object(helpers["c" /* includes */])(defaultKeys, key))
            invalid.push(key);
    });
    if (invalid.length) {
        throw new Error('Invalid options: ' + invalid.join(', '));
    }
    return __assign(__assign({}, rrulestr_DEFAULT_OPTIONS), options);
}
function extractName(line) {
    if (line.indexOf(':') === -1) {
        return {
            name: 'RRULE',
            value: line
        };
    }
    var _a = Object(helpers["m" /* split */])(line, ':', 1), name = _a[0], value = _a[1];
    return {
        name: name,
        value: value
    };
}
function breakDownLine(line) {
    var _a = extractName(line), name = _a.name, value = _a.value;
    var parms = name.split(';');
    if (!parms)
        throw new Error('empty property name');
    return {
        name: parms[0].toUpperCase(),
        parms: parms.slice(1),
        value: value
    };
}
function splitIntoLines(s, unfold) {
    if (unfold === void 0) { unfold = false; }
    s = s && s.trim();
    if (!s)
        throw new Error('Invalid empty string');
    // More info about 'unfold' option
    // Go head to http://www.ietf.org/rfc/rfc2445.txt
    if (!unfold) {
        return s.split(/\s/);
    }
    var lines = s.split('\n');
    var i = 0;
    while (i < lines.length) {
        // TODO
        var line = (lines[i] = lines[i].replace(/\s+$/g, ''));
        if (!line) {
            lines.splice(i, 1);
        }
        else if (i > 0 && line[0] === ' ') {
            lines[i - 1] += line.slice(1);
            lines.splice(i, 1);
        }
        else {
            i += 1;
        }
    }
    return lines;
}
function validateDateParm(parms) {
    parms.forEach(function (parm) {
        if (!/(VALUE=DATE(-TIME)?)|(TZID=)/.test(parm)) {
            throw new Error('unsupported RDATE/EXDATE parm: ' + parm);
        }
    });
}
function parseRDate(rdateval, parms) {
    validateDateParm(parms);
    return rdateval
        .split(',')
        .map(function (datestr) { return src_dateutil.untilStringToDate(datestr); });
}

// CONCATENATED MODULE: ./src/rruleset.ts







function createGetterSetter(fieldName) {
    var _this = this;
    return function (field) {
        if (field !== undefined) {
            _this["_" + fieldName] = field;
        }
        if (_this["_" + fieldName] !== undefined) {
            return _this["_" + fieldName];
        }
        for (var i = 0; i < _this._rrule.length; i++) {
            var field_1 = _this._rrule[i].origOptions[fieldName];
            if (field_1) {
                return field_1;
            }
        }
    };
}
var rruleset_RRuleSet = /** @class */ (function (_super) {
    __extends(RRuleSet, _super);
    /**
     *
     * @param {Boolean?} noCache
     *  The same stratagy as RRule on cache, default to false
     * @constructor
     */
    function RRuleSet(noCache) {
        if (noCache === void 0) { noCache = false; }
        var _this = _super.call(this, {}, noCache) || this;
        _this.dtstart = createGetterSetter.apply(_this, ['dtstart']);
        _this.tzid = createGetterSetter.apply(_this, ['tzid']);
        _this._rrule = [];
        _this._rdate = [];
        _this._exrule = [];
        _this._exdate = [];
        return _this;
    }
    RRuleSet.prototype._iter = function (iterResult) {
        return iterSet(iterResult, this._rrule, this._exrule, this._rdate, this._exdate, this.tzid());
    };
    /**
     * Adds an RRule to the set
     *
     * @param {RRule}
     */
    RRuleSet.prototype.rrule = function (rrule) {
        _addRule(rrule, this._rrule);
    };
    /**
     * Adds an EXRULE to the set
     *
     * @param {RRule}
     */
    RRuleSet.prototype.exrule = function (rrule) {
        _addRule(rrule, this._exrule);
    };
    /**
     * Adds an RDate to the set
     *
     * @param {Date}
     */
    RRuleSet.prototype.rdate = function (date) {
        _addDate(date, this._rdate);
    };
    /**
     * Adds an EXDATE to the set
     *
     * @param {Date}
     */
    RRuleSet.prototype.exdate = function (date) {
        _addDate(date, this._exdate);
    };
    /**
     * Get list of included rrules in this recurrence set.
     *
     * @return List of rrules
     */
    RRuleSet.prototype.rrules = function () {
        return this._rrule.map(function (e) { return rrulestr(e.toString()); });
    };
    /**
     * Get list of excluded rrules in this recurrence set.
     *
     * @return List of exrules
     */
    RRuleSet.prototype.exrules = function () {
        return this._exrule.map(function (e) { return rrulestr(e.toString()); });
    };
    /**
     * Get list of included datetimes in this recurrence set.
     *
     * @return List of rdates
     */
    RRuleSet.prototype.rdates = function () {
        return this._rdate.map(function (e) { return new Date(e.getTime()); });
    };
    /**
     * Get list of included datetimes in this recurrence set.
     *
     * @return List of exdates
     */
    RRuleSet.prototype.exdates = function () {
        return this._exdate.map(function (e) { return new Date(e.getTime()); });
    };
    RRuleSet.prototype.valueOf = function () {
        var result = [];
        if (!this._rrule.length && this._dtstart) {
            result = result.concat(optionsToString({ dtstart: this._dtstart }));
        }
        this._rrule.forEach(function (rrule) {
            result = result.concat(rrule.toString().split('\n'));
        });
        this._exrule.forEach(function (exrule) {
            result = result.concat(exrule.toString().split('\n')
                .map(function (line) { return line.replace(/^RRULE:/, 'EXRULE:'); })
                .filter(function (line) { return !/^DTSTART/.test(line); }));
        });
        if (this._rdate.length) {
            result.push(rdatesToString('RDATE', this._rdate, this.tzid()));
        }
        if (this._exdate.length) {
            result.push(rdatesToString('EXDATE', this._exdate, this.tzid()));
        }
        return result;
    };
    /**
     * to generate recurrence field such as:
     *   DTSTART:19970902T010000Z
     *   RRULE:FREQ=YEARLY;COUNT=2;BYDAY=TU
     *   RRULE:FREQ=YEARLY;COUNT=1;BYDAY=TH
     */
    RRuleSet.prototype.toString = function () {
        return this.valueOf().join('\n');
    };
    /**
     * Create a new RRuleSet Object completely base on current instance
     */
    RRuleSet.prototype.clone = function () {
        var rrs = new RRuleSet(!!this._cache);
        this._rrule.forEach(function (rule) { return rrs.rrule(rule.clone()); });
        this._exrule.forEach(function (rule) { return rrs.exrule(rule.clone()); });
        this._rdate.forEach(function (date) { return rrs.rdate(new Date(date.getTime())); });
        this._exdate.forEach(function (date) { return rrs.exdate(new Date(date.getTime())); });
        return rrs;
    };
    return RRuleSet;
}(src_rrule));
/* harmony default export */ var rruleset = (rruleset_RRuleSet);
function _addRule(rrule, collection) {
    if (!(rrule instanceof src_rrule)) {
        throw new TypeError(String(rrule) + ' is not RRule instance');
    }
    if (!Object(helpers["c" /* includes */])(collection.map(String), String(rrule))) {
        collection.push(rrule);
    }
}
function _addDate(date, collection) {
    if (!(date instanceof Date)) {
        throw new TypeError(String(date) + ' is not Date instance');
    }
    if (!Object(helpers["c" /* includes */])(collection.map(Number), Number(date))) {
        collection.push(date);
        src_dateutil.sort(collection);
    }
}
function rdatesToString(param, rdates, tzid) {
    var isUTC = !tzid || tzid.toUpperCase() === 'UTC';
    var header = isUTC ? param + ":" : param + ";TZID=" + tzid + ":";
    var dateString = rdates
        .map(function (rdate) { return src_dateutil.timeToUntilString(rdate.valueOf(), isUTC); })
        .join(',');
    return "" + header + dateString;
}

// CONCATENATED MODULE: ./src/index.ts
/* concated harmony reexport rrulestr */__webpack_require__.d(__webpack_exports__, "rrulestr", function() { return rrulestr; });
/* concated harmony reexport Frequency */__webpack_require__.d(__webpack_exports__, "Frequency", function() { return Frequency; });
/* concated harmony reexport Weekday */__webpack_require__.d(__webpack_exports__, "Weekday", function() { return weekday["b" /* Weekday */]; });
/* concated harmony reexport RRule */__webpack_require__.d(__webpack_exports__, "RRule", function() { return src_rrule; });
/* concated harmony reexport RRuleSet */__webpack_require__.d(__webpack_exports__, "RRuleSet", function() { return rruleset; });
/*!
 * rrule.js - Library for working with recurrence rules for calendar dates.
 * https://github.com/jakubroztocil/rrule
 *
 * Copyright 2010, Jakub Roztocil and Lars Schoning
 * Licenced under the BSD licence.
 * https://github.com/jakubroztocil/rrule/blob/master/LICENCE
 *
 * Based on:
 * python-dateutil - Extensions to the standard Python datetime module.
 * Copyright (c) 2003-2011 - Gustavo Niemeyer <gustavo@niemeyer.net>
 * Copyright (c) 2012 - Tomi Pieviläinen <tomi.pievilainen@iki.fi>
 * https://github.com/jakubroztocil/rrule/blob/master/LICENCE
 *
 */






/* harmony default export */ var src = __webpack_exports__["default"] = (src_rrule);


/***/ }),
/* 2 */
/***/ (function(module, __webpack_exports__, __webpack_require__) {

"use strict";
/* harmony export (binding) */ __webpack_require__.d(__webpack_exports__, "a", function() { return ALL_WEEKDAYS; });
/* harmony export (binding) */ __webpack_require__.d(__webpack_exports__, "b", function() { return Weekday; });
// =============================================================================
// Weekday
// =============================================================================
var ALL_WEEKDAYS = ['MO', 'TU', 'WE', 'TH', 'FR', 'SA', 'SU'];
var Weekday = /** @class */ (function () {
    function Weekday(weekday, n) {
        if (n === 0)
            throw new Error("Can't create weekday with n == 0");
        this.weekday = weekday;
        this.n = n;
    }
    Weekday.fromStr = function (str) {
        return new Weekday(ALL_WEEKDAYS.indexOf(str));
    };
    // __call__ - Cannot call the object directly, do it through
    // e.g. RRule.TH.nth(-1) instead,
    Weekday.prototype.nth = function (n) {
        return this.n === n ? this : new Weekday(this.weekday, n);
    };
    // __eq__
    Weekday.prototype.equals = function (other) {
        return this.weekday === other.weekday && this.n === other.n;
    };
    // __repr__
    Weekday.prototype.toString = function () {
        var s = ALL_WEEKDAYS[this.weekday];
        if (this.n)
            s = (this.n > 0 ? '+' : '') + String(this.n) + s;
        return s;
    };
    Weekday.prototype.getJsWeekday = function () {
        return this.weekday === 6 ? 0 : this.weekday + 1;
    };
    return Weekday;
}());



/***/ }),
/* 3 */
/***/ (function(module, __webpack_exports__, __webpack_require__) {

"use strict";
__webpack_require__.r(__webpack_exports__);

// CONCATENATED MODULE: ./src/nlp/i18n.ts
// =============================================================================
// i18n
// =============================================================================
var ENGLISH = {
    dayNames: [
        'Sunday', 'Monday', 'Tuesday', 'Wednesday',
        'Thursday', 'Friday', 'Saturday'
    ],
    monthNames: [
        'January', 'February', 'March', 'April', 'May',
        'June', 'July', 'August', 'September', 'October',
        'November', 'December'
    ],
    tokens: {
        'SKIP': /^[ \r\n\t]+|^\.$/,
        'number': /^[1-9][0-9]*/,
        'numberAsText': /^(one|two|three)/i,
        'every': /^every/i,
        'day(s)': /^days?/i,
        'weekday(s)': /^weekdays?/i,
        'week(s)': /^weeks?/i,
        'hour(s)': /^hours?/i,
        'minute(s)': /^minutes?/i,
        'month(s)': /^months?/i,
        'year(s)': /^years?/i,
        'on': /^(on|in)/i,
        'at': /^(at)/i,
        'the': /^the/i,
        'first': /^first/i,
        'second': /^second/i,
        'third': /^third/i,
        'nth': /^([1-9][0-9]*)(\.|th|nd|rd|st)/i,
        'last': /^last/i,
        'for': /^for/i,
        'time(s)': /^times?/i,
        'until': /^(un)?til/i,
        'monday': /^mo(n(day)?)?/i,
        'tuesday': /^tu(e(s(day)?)?)?/i,
        'wednesday': /^we(d(n(esday)?)?)?/i,
        'thursday': /^th(u(r(sday)?)?)?/i,
        'friday': /^fr(i(day)?)?/i,
        'saturday': /^sa(t(urday)?)?/i,
        'sunday': /^su(n(day)?)?/i,
        'january': /^jan(uary)?/i,
        'february': /^feb(ruary)?/i,
        'march': /^mar(ch)?/i,
        'april': /^apr(il)?/i,
        'may': /^may/i,
        'june': /^june?/i,
        'july': /^july?/i,
        'august': /^aug(ust)?/i,
        'september': /^sep(t(ember)?)?/i,
        'october': /^oct(ober)?/i,
        'november': /^nov(ember)?/i,
        'december': /^dec(ember)?/i,
        'comma': /^(,\s*|(and|or)\s*)+/i
    }
};
/* harmony default export */ var i18n = (ENGLISH);

// EXTERNAL MODULE: ./src/index.ts + 23 modules
var src = __webpack_require__(1);

// EXTERNAL MODULE: ./src/helpers.ts
var helpers = __webpack_require__(0);

// CONCATENATED MODULE: ./src/nlp/totext.ts



// =============================================================================
// Helper functions
// =============================================================================
/**
 * Return true if a value is in an array
 */
var contains = function (arr, val) {
    return arr.indexOf(val) !== -1;
};
var defaultGetText = function (id) { return id.toString(); };
var defaultDateFormatter = function (year, month, day) { return month + " " + day + ", " + year; };
/**
 *
 * @param {RRule} rrule
 * Optional:
 * @param {Function} gettext function
 * @param {Object} language definition
 * @constructor
 */
var totext_ToText = /** @class */ (function () {
    function ToText(rrule, gettext, language, dateFormatter) {
        if (gettext === void 0) { gettext = defaultGetText; }
        if (language === void 0) { language = i18n; }
        if (dateFormatter === void 0) { dateFormatter = defaultDateFormatter; }
        this.text = [];
        this.language = language || i18n;
        this.gettext = gettext;
        this.dateFormatter = dateFormatter;
        this.rrule = rrule;
        this.options = rrule.options;
        this.origOptions = rrule.origOptions;
        if (this.origOptions.bymonthday) {
            var bymonthday = [].concat(this.options.bymonthday);
            var bynmonthday = [].concat(this.options.bynmonthday);
            bymonthday.sort(function (a, b) { return a - b; });
            bynmonthday.sort(function (a, b) { return b - a; });
            // 1, 2, 3, .., -5, -4, -3, ..
            this.bymonthday = bymonthday.concat(bynmonthday);
            if (!this.bymonthday.length)
                this.bymonthday = null;
        }
        if (Object(helpers["f" /* isPresent */])(this.origOptions.byweekday)) {
            var byweekday = !Object(helpers["d" /* isArray */])(this.origOptions.byweekday)
                ? [this.origOptions.byweekday]
                : this.origOptions.byweekday;
            var days = String(byweekday);
            this.byweekday = {
                allWeeks: byweekday.filter(function (weekday) {
                    return !weekday.n;
                }),
                someWeeks: byweekday.filter(function (weekday) {
                    return Boolean(weekday.n);
                }),
                isWeekdays: days.indexOf('MO') !== -1 &&
                    days.indexOf('TU') !== -1 &&
                    days.indexOf('WE') !== -1 &&
                    days.indexOf('TH') !== -1 &&
                    days.indexOf('FR') !== -1 &&
                    days.indexOf('SA') === -1 &&
                    days.indexOf('SU') === -1,
                isEveryDay: days.indexOf('MO') !== -1 &&
                    days.indexOf('TU') !== -1 &&
                    days.indexOf('WE') !== -1 &&
                    days.indexOf('TH') !== -1 &&
                    days.indexOf('FR') !== -1 &&
                    days.indexOf('SA') !== -1 &&
                    days.indexOf('SU') !== -1
            };
            var sortWeekDays = function (a, b) {
                return a.weekday - b.weekday;
            };
            this.byweekday.allWeeks.sort(sortWeekDays);
            this.byweekday.someWeeks.sort(sortWeekDays);
            if (!this.byweekday.allWeeks.length)
                this.byweekday.allWeeks = null;
            if (!this.byweekday.someWeeks.length)
                this.byweekday.someWeeks = null;
        }
        else {
            this.byweekday = null;
        }
    }
    /**
     * Test whether the rrule can be fully converted to text.
     * @param {RRule} rrule
     * @return {Boolean}
     */
    ToText.isFullyConvertible = function (rrule) {
        var canConvert = true;
        if (!(rrule.options.freq in ToText.IMPLEMENTED))
            return false;
        if (rrule.origOptions.until && rrule.origOptions.count)
            return false;
        for (var key in rrule.origOptions) {
            if (contains(['dtstart', 'wkst', 'freq'], key))
                return true;
            if (!contains(ToText.IMPLEMENTED[rrule.options.freq], key))
                return false;
        }
        return canConvert;
    };
    ToText.prototype.isFullyConvertible = function () {
        return ToText.isFullyConvertible(this.rrule);
    };
    /**
     * Perform the conversion. Only some of the frequencies are supported.
     * If some of the rrule's options aren't supported, they'll
     * be omitted from the output an "(~ approximate)" will be appended.
     * @return {*}
     */
    ToText.prototype.toString = function () {
        var gettext = this.gettext;
        if (!(this.options.freq in ToText.IMPLEMENTED)) {
            return gettext('RRule error: Unable to fully convert this rrule to text');
        }
        this.text = [gettext('every')];
        // @ts-ignore
        this[src["default"].FREQUENCIES[this.options.freq]]();
        if (this.options.until) {
            this.add(gettext('until'));
            var until = this.options.until;
            this.add(this.dateFormatter(until.getUTCFullYear(), this.language.monthNames[until.getUTCMonth()], until.getUTCDate()));
        }
        else if (this.options.count) {
            this.add(gettext('for'))
                .add(this.options.count.toString())
                .add(this.plural(this.options.count) ? gettext('times') : gettext('time'));
        }
        if (!this.isFullyConvertible())
            this.add(gettext('(~ approximate)'));
        return this.text.join('');
    };
    ToText.prototype.HOURLY = function () {
        var gettext = this.gettext;
        if (this.options.interval !== 1)
            this.add(this.options.interval.toString());
        this.add(this.plural(this.options.interval) ? gettext('hours') : gettext('hour'));
    };
    ToText.prototype.MINUTELY = function () {
        var gettext = this.gettext;
        if (this.options.interval !== 1)
            this.add(this.options.interval.toString());
        this.add(this.plural(this.options.interval)
            ? gettext('minutes')
            : gettext('minute'));
    };
    ToText.prototype.DAILY = function () {
        var gettext = this.gettext;
        if (this.options.interval !== 1)
            this.add(this.options.interval.toString());
        if (this.byweekday && this.byweekday.isWeekdays) {
            this.add(this.plural(this.options.interval)
                ? gettext('weekdays')
                : gettext('weekday'));
        }
        else {
            this.add(this.plural(this.options.interval) ? gettext('days') : gettext('day'));
        }
        if (this.origOptions.bymonth) {
            this.add(gettext('in'));
            this._bymonth();
        }
        if (this.bymonthday) {
            this._bymonthday();
        }
        else if (this.byweekday) {
            this._byweekday();
        }
        else if (this.origOptions.byhour) {
            this._byhour();
        }
    };
    ToText.prototype.WEEKLY = function () {
        var gettext = this.gettext;
        if (this.options.interval !== 1) {
            this.add(this.options.interval.toString()).add(this.plural(this.options.interval) ? gettext('weeks') : gettext('week'));
        }
        if (this.byweekday && this.byweekday.isWeekdays) {
            if (this.options.interval === 1) {
                this.add(this.plural(this.options.interval)
                    ? gettext('weekdays')
                    : gettext('weekday'));
            }
            else {
                this.add(gettext('on')).add(gettext('weekdays'));
            }
        }
        else if (this.byweekday && this.byweekday.isEveryDay) {
            this.add(this.plural(this.options.interval) ? gettext('days') : gettext('day'));
        }
        else {
            if (this.options.interval === 1)
                this.add(gettext('week'));
            if (this.origOptions.bymonth) {
                this.add(gettext('in'));
                this._bymonth();
            }
            if (this.bymonthday) {
                this._bymonthday();
            }
            else if (this.byweekday) {
                this._byweekday();
            }
        }
    };
    ToText.prototype.MONTHLY = function () {
        var gettext = this.gettext;
        if (this.origOptions.bymonth) {
            if (this.options.interval !== 1) {
                this.add(this.options.interval.toString()).add(gettext('months'));
                if (this.plural(this.options.interval))
                    this.add(gettext('in'));
            }
            else {
                // this.add(gettext('MONTH'))
            }
            this._bymonth();
        }
        else {
            if (this.options.interval !== 1)
                this.add(this.options.interval.toString());
            this.add(this.plural(this.options.interval)
                ? gettext('months')
                : gettext('month'));
        }
        if (this.bymonthday) {
            this._bymonthday();
        }
        else if (this.byweekday && this.byweekday.isWeekdays) {
            this.add(gettext('on')).add(gettext('weekdays'));
        }
        else if (this.byweekday) {
            this._byweekday();
        }
    };
    ToText.prototype.YEARLY = function () {
        var gettext = this.gettext;
        if (this.origOptions.bymonth) {
            if (this.options.interval !== 1) {
                this.add(this.options.interval.toString());
                this.add(gettext('years'));
            }
            else {
                // this.add(gettext('YEAR'))
            }
            this._bymonth();
        }
        else {
            if (this.options.interval !== 1)
                this.add(this.options.interval.toString());
            this.add(this.plural(this.options.interval) ? gettext('years') : gettext('year'));
        }
        if (this.bymonthday) {
            this._bymonthday();
        }
        else if (this.byweekday) {
            this._byweekday();
        }
        if (this.options.byyearday) {
            this.add(gettext('on the'))
                .add(this.list(this.options.byyearday, this.nth, gettext('and')))
                .add(gettext('day'));
        }
        if (this.options.byweekno) {
            this.add(gettext('in'))
                .add(this.plural(this.options.byweekno.length)
                ? gettext('weeks')
                : gettext('week'))
                .add(this.list(this.options.byweekno, undefined, gettext('and')));
        }
    };
    ToText.prototype._bymonthday = function () {
        var gettext = this.gettext;
        if (this.byweekday && this.byweekday.allWeeks) {
            this.add(gettext('on'))
                .add(this.list(this.byweekday.allWeeks, this.weekdaytext, gettext('or')))
                .add(gettext('the'))
                .add(this.list(this.bymonthday, this.nth, gettext('or')));
        }
        else {
            this.add(gettext('on the')).add(this.list(this.bymonthday, this.nth, gettext('and')));
        }
        // this.add(gettext('DAY'))
    };
    ToText.prototype._byweekday = function () {
        var gettext = this.gettext;
        if (this.byweekday.allWeeks && !this.byweekday.isWeekdays) {
            this.add(gettext('on')).add(this.list(this.byweekday.allWeeks, this.weekdaytext));
        }
        if (this.byweekday.someWeeks) {
            if (this.byweekday.allWeeks)
                this.add(gettext('and'));
            this.add(gettext('on the')).add(this.list(this.byweekday.someWeeks, this.weekdaytext, gettext('and')));
        }
    };
    ToText.prototype._byhour = function () {
        var gettext = this.gettext;
        this.add(gettext('at')).add(this.list(this.origOptions.byhour, undefined, gettext('and')));
    };
    ToText.prototype._bymonth = function () {
        this.add(this.list(this.options.bymonth, this.monthtext, this.gettext('and')));
    };
    ToText.prototype.nth = function (n) {
        n = parseInt(n.toString(), 10);
        var nth;
        var npos;
        var gettext = this.gettext;
        if (n === -1)
            return gettext('last');
        npos = Math.abs(n);
        switch (npos) {
            case 1:
            case 21:
            case 31:
                nth = npos + gettext('st');
                break;
            case 2:
            case 22:
                nth = npos + gettext('nd');
                break;
            case 3:
            case 23:
                nth = npos + gettext('rd');
                break;
            default:
                nth = npos + gettext('th');
        }
        return n < 0 ? nth + ' ' + gettext('last') : nth;
    };
    ToText.prototype.monthtext = function (m) {
        return this.language.monthNames[m - 1];
    };
    ToText.prototype.weekdaytext = function (wday) {
        var weekday = Object(helpers["e" /* isNumber */])(wday) ? (wday + 1) % 7 : wday.getJsWeekday();
        return ((wday.n ? this.nth(wday.n) + ' ' : '') + this.language.dayNames[weekday]);
    };
    ToText.prototype.plural = function (n) {
        return n % 100 !== 1;
    };
    ToText.prototype.add = function (s) {
        this.text.push(' ');
        this.text.push(s);
        return this;
    };
    ToText.prototype.list = function (arr, callback, finalDelim, delim) {
        if (delim === void 0) { delim = ','; }
        if (!Object(helpers["d" /* isArray */])(arr)) {
            arr = [arr];
        }
        var delimJoin = function (array, delimiter, finalDelimiter) {
            var list = '';
            for (var i = 0; i < array.length; i++) {
                if (i !== 0) {
                    if (i === array.length - 1) {
                        list += ' ' + finalDelimiter + ' ';
                    }
                    else {
                        list += delimiter + ' ';
                    }
                }
                list += array[i];
            }
            return list;
        };
        callback =
            callback ||
                function (o) {
                    return o.toString();
                };
        var self = this;
        var realCallback = function (arg) {
            return callback && callback.call(self, arg);
        };
        if (finalDelim) {
            return delimJoin(arr.map(realCallback), delim, finalDelim);
        }
        else {
            return arr.map(realCallback).join(delim + ' ');
        }
    };
    return ToText;
}());
/* harmony default export */ var totext = (totext_ToText);

// CONCATENATED MODULE: ./src/nlp/parsetext.ts


// =============================================================================
// Parser
// =============================================================================
var Parser = /** @class */ (function () {
    function Parser(rules) {
        this.done = true;
        this.rules = rules;
    }
    Parser.prototype.start = function (text) {
        this.text = text;
        this.done = false;
        return this.nextSymbol();
    };
    Parser.prototype.isDone = function () {
        return this.done && this.symbol === null;
    };
    Parser.prototype.nextSymbol = function () {
        var best;
        var bestSymbol;
        var p = this;
        this.symbol = null;
        this.value = null;
        do {
            if (this.done)
                return false;
            var rule = void 0;
            best = null;
            for (var name_1 in this.rules) {
                rule = this.rules[name_1];
                var match = rule.exec(p.text);
                if (match) {
                    if (best === null || match[0].length > best[0].length) {
                        best = match;
                        bestSymbol = name_1;
                    }
                }
            }
            if (best != null) {
                this.text = this.text.substr(best[0].length);
                if (this.text === '')
                    this.done = true;
            }
            if (best == null) {
                this.done = true;
                this.symbol = null;
                this.value = null;
                return;
            }
            // @ts-ignore
        } while (bestSymbol === 'SKIP');
        // @ts-ignore
        this.symbol = bestSymbol;
        this.value = best;
        return true;
    };
    Parser.prototype.accept = function (name) {
        if (this.symbol === name) {
            if (this.value) {
                var v = this.value;
                this.nextSymbol();
                return v;
            }
            this.nextSymbol();
            return true;
        }
        return false;
    };
    Parser.prototype.acceptNumber = function () {
        return this.accept('number');
    };
    Parser.prototype.expect = function (name) {
        if (this.accept(name))
            return true;
        throw new Error('expected ' + name + ' but found ' + this.symbol);
    };
    return Parser;
}());
function parseText(text, language) {
    if (language === void 0) { language = i18n; }
    var options = {};
    var ttr = new Parser(language.tokens);
    if (!ttr.start(text))
        return null;
    S();
    return options;
    function S() {
        // every [n]
        ttr.expect('every');
        var n = ttr.acceptNumber();
        if (n)
            options.interval = parseInt(n[0], 10);
        if (ttr.isDone())
            throw new Error('Unexpected end');
        switch (ttr.symbol) {
            case 'day(s)':
                options.freq = src["default"].DAILY;
                if (ttr.nextSymbol()) {
                    AT();
                    F();
                }
                break;
            // FIXME Note: every 2 weekdays != every two weeks on weekdays.
            // DAILY on weekdays is not a valid rule
            case 'weekday(s)':
                options.freq = src["default"].WEEKLY;
                options.byweekday = [
                    src["default"].MO,
                    src["default"].TU,
                    src["default"].WE,
                    src["default"].TH,
                    src["default"].FR
                ];
                ttr.nextSymbol();
                F();
                break;
            case 'week(s)':
                options.freq = src["default"].WEEKLY;
                if (ttr.nextSymbol()) {
                    ON();
                    F();
                }
                break;
            case 'hour(s)':
                options.freq = src["default"].HOURLY;
                if (ttr.nextSymbol()) {
                    ON();
                    F();
                }
                break;
            case 'minute(s)':
                options.freq = src["default"].MINUTELY;
                if (ttr.nextSymbol()) {
                    ON();
                    F();
                }
                break;
            case 'month(s)':
                options.freq = src["default"].MONTHLY;
                if (ttr.nextSymbol()) {
                    ON();
                    F();
                }
                break;
            case 'year(s)':
                options.freq = src["default"].YEARLY;
                if (ttr.nextSymbol()) {
                    ON();
                    F();
                }
                break;
            case 'monday':
            case 'tuesday':
            case 'wednesday':
            case 'thursday':
            case 'friday':
            case 'saturday':
            case 'sunday':
                options.freq = src["default"].WEEKLY;
                var key = ttr.symbol.substr(0, 2).toUpperCase();
                options.byweekday = [src["default"][key]];
                if (!ttr.nextSymbol())
                    return;
                // TODO check for duplicates
                while (ttr.accept('comma')) {
                    if (ttr.isDone())
                        throw new Error('Unexpected end');
                    var wkd = decodeWKD();
                    if (!wkd) {
                        throw new Error('Unexpected symbol ' + ttr.symbol + ', expected weekday');
                    }
                    // @ts-ignore
                    options.byweekday.push(src["default"][wkd]);
                    ttr.nextSymbol();
                }
                MDAYs();
                F();
                break;
            case 'january':
            case 'february':
            case 'march':
            case 'april':
            case 'may':
            case 'june':
            case 'july':
            case 'august':
            case 'september':
            case 'october':
            case 'november':
            case 'december':
                options.freq = src["default"].YEARLY;
                options.bymonth = [decodeM()];
                if (!ttr.nextSymbol())
                    return;
                // TODO check for duplicates
                while (ttr.accept('comma')) {
                    if (ttr.isDone())
                        throw new Error('Unexpected end');
                    var m = decodeM();
                    if (!m) {
                        throw new Error('Unexpected symbol ' + ttr.symbol + ', expected month');
                    }
                    options.bymonth.push(m);
                    ttr.nextSymbol();
                }
                ON();
                F();
                break;
            default:
                throw new Error('Unknown symbol');
        }
    }
    function ON() {
        var on = ttr.accept('on');
        var the = ttr.accept('the');
        if (!(on || the))
            return;
        do {
            var nth = decodeNTH();
            var wkd = decodeWKD();
            var m = decodeM();
            // nth <weekday> | <weekday>
            if (nth) {
                // ttr.nextSymbol()
                if (wkd) {
                    ttr.nextSymbol();
                    if (!options.byweekday)
                        options.byweekday = [];
                    // @ts-ignore
                    options.byweekday.push(src["default"][wkd].nth(nth));
                }
                else {
                    if (!options.bymonthday)
                        options.bymonthday = [];
                    // @ts-ignore
                    options.bymonthday.push(nth);
                    ttr.accept('day(s)');
                }
                // <weekday>
            }
            else if (wkd) {
                ttr.nextSymbol();
                if (!options.byweekday)
                    options.byweekday = [];
                // @ts-ignore
                options.byweekday.push(src["default"][wkd]);
            }
            else if (ttr.symbol === 'weekday(s)') {
                ttr.nextSymbol();
                if (!options.byweekday) {
                    options.byweekday = [
                        src["default"].MO,
                        src["default"].TU,
                        src["default"].WE,
                        src["default"].TH,
                        src["default"].FR
                    ];
                }
            }
            else if (ttr.symbol === 'week(s)') {
                ttr.nextSymbol();
                var n = ttr.acceptNumber();
                if (!n) {
                    throw new Error('Unexpected symbol ' + ttr.symbol + ', expected week number');
                }
                options.byweekno = [parseInt(n[0], 10)];
                while (ttr.accept('comma')) {
                    n = ttr.acceptNumber();
                    if (!n) {
                        throw new Error('Unexpected symbol ' + ttr.symbol + '; expected monthday');
                    }
                    options.byweekno.push(parseInt(n[0], 10));
                }
            }
            else if (m) {
                ttr.nextSymbol();
                if (!options.bymonth)
                    options.bymonth = [];
                // @ts-ignore
                options.bymonth.push(m);
            }
            else {
                return;
            }
        } while (ttr.accept('comma') || ttr.accept('the') || ttr.accept('on'));
    }
    function AT() {
        var at = ttr.accept('at');
        if (!at)
            return;
        do {
            var n = ttr.acceptNumber();
            if (!n) {
                throw new Error('Unexpected symbol ' + ttr.symbol + ', expected hour');
            }
            options.byhour = [parseInt(n[0], 10)];
            while (ttr.accept('comma')) {
                n = ttr.acceptNumber();
                if (!n) {
                    throw new Error('Unexpected symbol ' + ttr.symbol + '; expected hour');
                }
                options.byhour.push(parseInt(n[0], 10));
            }
        } while (ttr.accept('comma') || ttr.accept('at'));
    }
    function decodeM() {
        switch (ttr.symbol) {
            case 'january':
                return 1;
            case 'february':
                return 2;
            case 'march':
                return 3;
            case 'april':
                return 4;
            case 'may':
                return 5;
            case 'june':
                return 6;
            case 'july':
                return 7;
            case 'august':
                return 8;
            case 'september':
                return 9;
            case 'october':
                return 10;
            case 'november':
                return 11;
            case 'december':
                return 12;
            default:
                return false;
        }
    }
    function decodeWKD() {
        switch (ttr.symbol) {
            case 'monday':
            case 'tuesday':
            case 'wednesday':
            case 'thursday':
            case 'friday':
            case 'saturday':
            case 'sunday':
                return ttr.symbol.substr(0, 2).toUpperCase();
            default:
                return false;
        }
    }
    function decodeNTH() {
        switch (ttr.symbol) {
            case 'last':
                ttr.nextSymbol();
                return -1;
            case 'first':
                ttr.nextSymbol();
                return 1;
            case 'second':
                ttr.nextSymbol();
                return ttr.accept('last') ? -2 : 2;
            case 'third':
                ttr.nextSymbol();
                return ttr.accept('last') ? -3 : 3;
            case 'nth':
                var v = parseInt(ttr.value[1], 10);
                if (v < -366 || v > 366)
                    throw new Error('Nth out of range: ' + v);
                ttr.nextSymbol();
                return ttr.accept('last') ? -v : v;
            default:
                return false;
        }
    }
    function MDAYs() {
        ttr.accept('on');
        ttr.accept('the');
        var nth = decodeNTH();
        if (!nth)
            return;
        options.bymonthday = [nth];
        ttr.nextSymbol();
        while (ttr.accept('comma')) {
            nth = decodeNTH();
            if (!nth) {
                throw new Error('Unexpected symbol ' + ttr.symbol + '; expected monthday');
            }
            options.bymonthday.push(nth);
            ttr.nextSymbol();
        }
    }
    function F() {
        if (ttr.symbol === 'until') {
            var date = Date.parse(ttr.text);
            if (!date)
                throw new Error('Cannot parse until date:' + ttr.text);
            options.until = new Date(date);
        }
        else if (ttr.accept('for')) {
            options.count = parseInt(ttr.value[0], 10);
            ttr.expect('number');
            // ttr.expect('times')
        }
    }
}

// CONCATENATED MODULE: ./src/nlp/index.ts
/* harmony export (binding) */ __webpack_require__.d(__webpack_exports__, "fromText", function() { return fromText; });
/* harmony export (binding) */ __webpack_require__.d(__webpack_exports__, "isFullyConvertible", function() { return isFullyConvertible; });
/* harmony export (binding) */ __webpack_require__.d(__webpack_exports__, "toText", function() { return toText; });
/* concated harmony reexport parseText */__webpack_require__.d(__webpack_exports__, "parseText", function() { return parseText; });




/*!
* rrule.js - Library for working with recurrence rules for calendar dates.
* https://github.com/jakubroztocil/rrule
*
* Copyright 2010, Jakub Roztocil and Lars Schoning
* Licenced under the BSD licence.
* https://github.com/jakubroztocil/rrule/blob/master/LICENCE
*
*/
/**
 *
 * Implementation of RRule.fromText() and RRule::toText().
 *
 *
 * On the client side, this file needs to be included
 * when those functions are used.
 *
 */
// =============================================================================
// fromText
// =============================================================================
/**
 * Will be able to convert some of the below described rules from
 * text format to a rule object.
 *
 *
 * RULES
 *
 * Every ([n])
 *       day(s)
 *     | [weekday], ..., (and) [weekday]
 *     | weekday(s)
 *     | week(s)
 *     | month(s)
 *     | [month], ..., (and) [month]
 *     | year(s)
 *
 *
 * Plus 0, 1, or multiple of these:
 *
 * on [weekday], ..., (or) [weekday] the [monthday], [monthday], ... (or) [monthday]
 *
 * on [weekday], ..., (and) [weekday]
 *
 * on the [monthday], [monthday], ... (and) [monthday] (day of the month)
 *
 * on the [nth-weekday], ..., (and) [nth-weekday] (of the month/year)
 *
 *
 * Plus 0 or 1 of these:
 *
 * for [n] time(s)
 *
 * until [date]
 *
 * Plus (.)
 *
 *
 * Definitely no supported for parsing:
 *
 * (for year):
 *     in week(s) [n], ..., (and) [n]
 *
 *     on the [yearday], ..., (and) [n] day of the year
 *     on day [yearday], ..., (and) [n]
 *
 *
 * NON-TERMINALS
 *
 * [n]: 1, 2 ..., one, two, three ..
 * [month]: January, February, March, April, May, ... December
 * [weekday]: Monday, ... Sunday
 * [nth-weekday]: first [weekday], 2nd [weekday], ... last [weekday], ...
 * [monthday]: first, 1., 2., 1st, 2nd, second, ... 31st, last day, 2nd last day, ..
 * [date]:
 *     [month] (0-31(,) ([year])),
 *     (the) 0-31.(1-12.([year])),
 *     (the) 0-31/(1-12/([year])),
 *     [weekday]
 *
 * [year]: 0000, 0001, ... 01, 02, ..
 *
 * Definitely not supported for parsing:
 *
 * [yearday]: first, 1., 2., 1st, 2nd, second, ... 366th, last day, 2nd last day, ..
 *
 * @param {String} text
 * @return {Object, Boolean} the rule, or null.
 */
var fromText = function (text, language) {
    if (language === void 0) { language = i18n; }
    return new src["default"](parseText(text, language) || undefined);
};
var common = [
    'count',
    'until',
    'interval',
    'byweekday',
    'bymonthday',
    'bymonth'
];
totext.IMPLEMENTED = [];
totext.IMPLEMENTED[src["default"].HOURLY] = common;
totext.IMPLEMENTED[src["default"].MINUTELY] = common;
totext.IMPLEMENTED[src["default"].DAILY] = ['byhour'].concat(common);
totext.IMPLEMENTED[src["default"].WEEKLY] = common;
totext.IMPLEMENTED[src["default"].MONTHLY] = common;
totext.IMPLEMENTED[src["default"].YEARLY] = ['byweekno', 'byyearday'].concat(common);
// =============================================================================
// Export
// =============================================================================
var toText = function (rrule, gettext, language, dateFormatter) {
    return new totext(rrule, gettext, language, dateFormatter).toString();
};
var isFullyConvertible = totext.isFullyConvertible;



/***/ })
/******/ ]);
});
//# sourceMappingURL=rrule.js.map