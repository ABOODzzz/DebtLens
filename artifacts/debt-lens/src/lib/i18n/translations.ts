import { common } from './dictionaries/common';
import { landing } from './dictionaries/landing';
import { login } from './dictionaries/login';
import { register } from './dictionaries/register';
import { notFound } from './dictionaries/not-found';
import { notifications } from './dictionaries/notifications';
import { wizard } from './dictionaries/wizard';
import { dashboard } from './dictionaries/dashboard';
import { admin } from './dictionaries/admin';

export type Language = 'ar' | 'en';

export const translations = {
  ar: {
    common: common.ar,
    landing: landing.ar,
    login: login.ar,
    register: register.ar,
    notFound: notFound.ar,
    notifications: notifications.ar,
    wizard: wizard.ar,
    dashboard: dashboard.ar,
    admin: admin.ar,
  },
  en: {
    common: common.en,
    landing: landing.en,
    login: login.en,
    register: register.en,
    notFound: notFound.en,
    notifications: notifications.en,
    wizard: wizard.en,
    dashboard: dashboard.en,
    admin: admin.en,
  },
};
