# jwgrootjen.com booking image.
# The published Easy!Appointments (GPLv3) release with the jwgrootjen.com theme
# and form customizations layered on top. Source: this repository.
FROM alextselegidis/easyappointments:1.6.0

# Theme + behaviour. asset_url() resolves to the .min variants in production.
COPY assets/css/jwg-booking.css      /var/www/html/assets/css/jwg-booking.css
COPY assets/css/jwg-booking.min.css  /var/www/html/assets/css/jwg-booking.min.css
COPY assets/js/jwg-booking.js        /var/www/html/assets/js/jwg-booking.js
COPY assets/js/jwg-booking.min.js    /var/www/html/assets/js/jwg-booking.min.js

# Customized views (theme include, footer, labels).
COPY application/views/layouts/booking_layout.php       /var/www/html/application/views/layouts/booking_layout.php
COPY application/views/components/booking_footer.php    /var/www/html/application/views/components/booking_footer.php
COPY application/views/components/booking_info_step.php /var/www/html/application/views/components/booking_info_step.php
COPY application/controllers/Captcha.php                 /var/www/html/application/controllers/Captcha.php
COPY application/views/components/booking_final_step.php /var/www/html/application/views/components/booking_final_step.php
