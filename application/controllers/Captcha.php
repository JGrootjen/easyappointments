<?php defined('BASEPATH') or exit('No direct script access allowed');

/* ----------------------------------------------------------------------------
 * Easy!Appointments - Online Appointment Scheduler
 *
 * @package     EasyAppointments
 * @author      A.Tselegidis <alextselegidis@gmail.com>
 * @copyright   Copyright (c) Alex Tselegidis
 * @license     https://opensource.org/licenses/GPL-3.0 - GPLv3
 * @link        https://easyappointments.org
 * @since       v1.0.0
 * ---------------------------------------------------------------------------- */

use Gregwar\Captcha\CaptchaBuilder;

/**
 * Captcha controller.
 *
 * Handles the captcha operations.
 *
 * @package Controllers
 */
class Captcha extends EA_Controller
{
    /**
     * Class Constructor
     */
    public function __construct()
    {
        parent::__construct();
    }

    /**
     * Make a page request to this method in order to output a fresh captcha image.
     */
    public function index(): void
    {
        method('get');

        // Arithmetic spam check rendered as an image (self-hosted, no third-party
        // service) to mirror the jwgrootjen.com contact-form captcha.
        $a = random_int(2, 9);
        $b = random_int(2, 9);
        session(['captcha_phrase' => (string) ($a + $b)]);

        $width = 160;
        $height = 50;
        $image = imagecreatetruecolor($width, $height);
        $bg = imagecolorallocate($image, 255, 255, 255);
        $ink = imagecolorallocate($image, 27, 39, 51);
        $faint = imagecolorallocate($image, 205, 214, 222);
        imagefilledrectangle($image, 0, 0, $width, $height, $bg);
        for ($i = 0; $i < 4; $i++) {
            imageline($image, random_int(0, $width), random_int(0, $height), random_int(0, $width), random_int(0, $height), $faint);
        }
        imagestring($image, 5, 28, 16, $a . '  +  ' . $b . '  = ?', $ink);
        header('Content-type: image/jpeg');
        imagejpeg($image);
        imagedestroy($image);
    }

    /**
     * Generate an ALTCHA challenge.
     */
    public function altcha_challenge(): void
    {
        try {
            method('get');

            $this->load->library('altcha_client');

            if (!$this->altcha_client->is_enabled()) {
                json_response([
                    'error' => 'ALTCHA is not enabled',
                ], 400);
                return;
            }

            $challenge = $this->altcha_client->create_challenge();

            json_response($challenge);
        } catch (Throwable $e) {
            json_exception($e);
        }
    }
}
