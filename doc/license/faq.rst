.. spelling:word-list::

   AGPL
   AGPLv3
   GPL
   LGPL
   Apache
   BSD
   MIT
   CLA
   django
   i18nfields
   hierarkey
   rami.io
   rami
   io
   GmbH

License FAQ
===========

.. warning::

   This FAQ tries to explain in simpler terms what the license of the pretix open source project does and does not
   allow. It is based on our interpretation of the license and is not legal advice. The contents of this page are not
   legally binding, only the original text of the license in the `license file`_ is legally binding.

How is pretix licensed?
-----------------------

pretix follows the popular dual licensing model. It is available under the `GNU Affero General Public License 3`_ (AGPL)
plus some additional terms, as well as under a proprietary license ("pretix Enterprise license") on request.

How can it be AGPL if there are additional terms?
-------------------------------------------------

Even though it is fairly unknown, the AGPL's section 7 is titled "Additional Terms" and outlines specific conditions
under which additional terms can be imposed on an AGPL-licensed work. In our case, we add three additional terms.

The first additional term for pretix is an additional **permission**. It allows you to do something that the AGPL would
generally not allow. As it doesn't restrict your freedoms granted by AGPL, if you don't like it, you can ignore it, and
if you distribute pretix further, you can remove it.

The second and third additional term for pretix are additional terms that restrict or specify other provisions of the
license. AGPL specifically requires that these terms can only restrict or specify very specific things and we believe
our additional terms are in compliance with that and are thus valid and may not be removed.

Why did you choose this license model?
--------------------------------------

pretix was born in the open source community and we're deeply committed to building the best open source ticketing
solution in the world. It is important to us that pretix is available with a comprehensive feature set under term that
are compatible with the `Open Source Definition`_. This enables event organizers from all industries and regions
to have access to a self-hosted, privacy-friendly and secure option to host their events.

However, developing and maintaining pretix is a lot of work. Between 2014 and 2021, we've received external
contributions from more than 150 individuals. Not counting translations over 90 % of the development was
done by staff engineers of rami.io GmbH, the company that started pretix. While we're very happy to receive many more
contributions in the future, we also want to ensure that we continue to be able to pay people working on pretix
full-time.

We believe our model creates a good balance between ensuring pretix is available freely as well as protecting our
business interests. Unlike licenses chosen by other projects recently, such as the Server-Side Public License, our
choice does not restrict using pretix for any possible use case, it just sets a few rules that you have to play by
if you do.

What do I need to do if I use pretix unmodified?
------------------------------------------------

If you use pretix without any modifications or plugins, you can use it for whatever you want, as long as you keep
all copyright notices (including the link to pretix at the bottom of the site) intact.

You are also allowed to make copies of the unmodified source code and distribute them to others as long as you keep
all copyright and license information intact.

If you install **plugins**, you must follow the same terms as when using a **modified** version (see below).

What do I need to do if I modify pretix?
----------------------------------------

If you want to modify pretix, you have the right to do so. However, you need to follow the following rules:

* If you **run it for your own events** (events run by you or your company as well as companies from the same
  corporate groups) our additional permission allows you to do so **without needing to share your source code
  modifications** as long as you keep the link to pretix at the bottom of the site intact.

* If you **run it for others**, for example as part of a Software-as-a-Service offering or a managed hosting service
  you **must** make the source code **including all your modifications and all installed plugins** available under the
  same license as pretix to every visitor of your site. You need to do so in a prominent place such as a link at the bottom of the
  site. You also **must** keep the existing link intact.
  You **may not** add additional restrictions on the result as a whole. You **may** add additional permissions, but
  only on the parts you added. You **must** make clear which changes you made and you must not give the impression that
  your modified version is an official version of pretix.

* If you **distribute** the modified version, for example as a source code or software package, you **must** license it
  under the AGPL license with the same additional terms. You **may not** add additional restrictions on the result as a
  whole. You **may** add additional permissions, but only on the parts you added. You **must** make clear which changes
  you made and you must not give the impression that your modified version is an official version of pretix.

Does the AGPL copyleft mechanism extend to plugins?
---------------------------------------------------

Yes. pretix plugins are tightly integrated with pretix, so when running pretix together with a plugin in the same
environment they form a `combined work`_ and the copyleft mechanism of AGPL applies.

Can I create proprietary or secret plugins?
-------------------------------------------

Yes, you can create a proprietary or secret plugin, but it may only ever be **used** in an environment that is covered
by the additional permission from our license. As soon as the plugin is installed in an installation that is not covered
by our additional permission (e.g. when it is used in a SaaS environment) or covered by an active pretix Enterprise
license it **must** be released to the visitors of the site under the same license as pretix (like a modified version
of pretix).

What licenses can plugins use?
------------------------------

Technically, you can distribute a plugin under any free or proprietary license as long as it is distributed separately.
However, once it is either **distributed together with pretix or used in an environment not covered by our
additional permission** or an active pretix Enterprise license, you **must** release it to all recipients of the
distribution or all visitors of your site under the same license as pretix (like a modified version of pretix).

If you release a plugin publicly, it is therefore most practical to use a license that is `compatible to AGPL`_.
This includes most open source licenses such as AGPL, GPL, Apache, 3-clause BSD or MIT.

Note however that when you license a plugin with pure AGPL, it will be incompatible with our additional permission.
Therefore, if you want to use an AGPL-licensed plugin, you'll need to publish the source code of **all** your plugins
under AGPL terms **even if you only use it for your own events**. A plugin would add its `own additional permission`_
to its license to allow combining it with pretix for this use case.

To make things less complicated, if you want to distribute a plugin freely, we therefore recommend distributing the
plugin under **Apache License 2.0**, like we do for most plugins we distribute as open source.

What do I need to do if I want to contribute my changes back?
-------------------------------------------------------------

In order to retain the possibility for us to offer pretix in a dual licensing model, we unfortunately need you to sign
a Contributor License Agreement (CLA) that gives us permission to use your contribution in all present and future
distributions of pretix. We know the bureaucracy sucks. Sorry.

What if I want to re-use a minor part of pretix in my project?
--------------------------------------------------------------

This is the main part we dislike about AGPL: If you see a specific thing in pretix that you'd like to use in another
project, you'll need to distribute your other project under AGPL terms as well which is often not practical.

In this case, feel free to get in touch with us! We're happy to grant you special permission or pull the component
out into a separately, permissively licensed repository. We already did that with `django-hierarkey`_ and
`django-i18nfield`_ which have previously been parts of pretix.

What can I use the name "pretix" for?
-------------------------------------

The name pretix is a registered trademark by rami.io GmbH.

* You **may** use it to **indicate copyright**, such as in the "powered by pretix" or "based on pretix" line, or when
  indicating that a distribution is based on pretix.

* You **may** use it to **indicate compatibility**, for example you are allowed to name your plugin "<name> for pretix"
  or you may state that an external service is compatible with pretix.

* You **may not** give the impression that your modified version, plugin or compatible service is official or authorized
  by rami.io GmbH or pretix unless we specifically allowed you to do so.

* You **may not** use it to name your modified version of pretix. End-users must be able to easily identify whether
  a version of pretix is distributed by us.

* You **may not** use any variations of the name, such as "MyPretix".

.. _license file: https://github.com/pretix/pretix/blob/master/LICENSE
.. _GNU Affero General Public License 3: https://www.gnu.org/licenses/agpl-3.0.en.html
.. _compatible to AGPL: https://www.gnu.org/licenses/license-list.en.html#GPLCompatibleLicenses
.. _Open Source Definition: https://opensource.org/osd
.. _combined work: https://www.gnu.org/licenses/gpl-faq.html#GPLPlugins
.. _own additional permission: https://www.gnu.org/licenses/gpl-faq.html#GPLIncompatibleLibs
.. _django-hierarkey: https://github.com/raphaelm/django-hierarkey
.. _django-i18nfield: https://github.com/raphaelm/django-i18nfield